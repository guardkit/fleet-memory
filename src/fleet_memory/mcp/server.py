"""FastMCP server core: context, lifespan, and tool registration.

Provides ServerContext (carrying store, writer, settings) and the factory
function create_mcp_server that builds a FastMCP instance. The server
starts even when Postgres is unreachable (lazy connection in lifespan).

Producer: TASK-MCP-001
Consumer: TASK-MCP-007 (final integration), Wave-3 tool tasks
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.settings import Settings
    from fleet_memory.writer.core import DeterministicWriter


@dataclass
class ServerContext:
    """Server context carrying dependencies for MCP tools.

    Holds the store, writer, and settings that tools will use.
    Can be constructed with None values for degraded/test mode.

    Attributes:
        store: AsyncPostgresStore instance (or None for degraded mode)
        writer: DeterministicWriter instance (or None for degraded mode)
        settings: Settings instance (or None for test mode)
    """

    store: AsyncPostgresStore | None
    writer: DeterministicWriter | None
    settings: Settings | None


def create_mcp_server(context: ServerContext, *, opens_store: bool = True) -> FastMCP:
    """Create a FastMCP server instance with the given context.

    Builds a FastMCP server configured for stdio transport. The server
    is constructed immediately, but connection to the store is deferred
    until the lifespan context manager is entered (lazy initialization).

    Args:
        context: ServerContext with dependencies (can have None values)
        opens_store: False for the sandbox's narrow door, a second server
            over the same context. It never opens the store: its tools read
            the shared context at call time, so they use the store the main
            server opened, and there is one database pool, not two.

    Returns:
        Configured FastMCP instance ready to run over stdio
    """

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        """Lifespan context manager: lazy store initialization.

        fastmcp invokes this with the server instance (LifespanCallable
        contract). Dependencies are published by mutating the shared
        ServerContext the tool closures hold — not via lifespan state,
        which fastmcp 3.x does not expose to plain @mcp.tool functions.

        Entry:
            - If context has a settings instance, builds store + writer
              and sets them on the shared context
            - Degraded mode (context.settings=None): leaves context as-is

        Exit:
            - Closes store connection pool cleanly and resets the context
        """
        # Degraded/test mode: context has None settings, or a store was
        # injected directly (tests) — use the provided context untouched.
        # The narrow door's server takes the same path: the main server owns
        # the store.
        if not opens_store or context.settings is None or context.store is not None:
            yield {
                "store": context.store,
                "writer": context.writer,
                "settings": context.settings,
            }
            return

        # Production mode: lazy store initialization
        import logging

        from fleet_memory.store import async_store_context
        from fleet_memory.writer.core import DeterministicWriter

        logger = logging.getLogger(__name__)

        # Enter store context (connects to Postgres, sets up embed callable).
        # A down store must NOT kill the server: the documented contract is
        # degraded mode — tools return structured infrastructure errors.
        # The failure is logged LOUDLY (2026-08-03: silent degradation hid a
        # month of dead memory; degraded is acceptable, quiet is not).
        try:
            store_cm = async_store_context(context.settings)
            store = await store_cm.__aenter__()
        except Exception:
            logger.exception(
                "MEMORY DEGRADED: store unreachable — serving structured "
                "errors instead of memory. Fix the store connection."
            )
            yield {"store": None, "writer": None, "settings": context.settings}
            return

        context.store = store
        context.writer = DeterministicWriter(store=store, settings=context.settings)
        try:
            yield {
                "store": context.store,
                "writer": context.writer,
                "settings": context.settings,
            }
        finally:
            # Reset so a stopped server never leaves tools holding a
            # closed pool; async_store_context closes the pool itself.
            context.store = None
            context.writer = None
            await store_cm.__aexit__(None, None, None)

    # Create FastMCP instance with lifespan
    # Name identifies this server in MCP client logs
    mcp = FastMCP("fleet-memory", lifespan=lifespan)

    return mcp


def register_all(
    mcp: FastMCP,
    context: ServerContext,
    *,
    sandbox: bool = False,
    allowed_projects: frozenset[str] | None = None,
) -> None:
    """Register all MCP tools and resources on the given server instance.

    Extension point for Wave-3 tool registration tasks. Each tool task
    will add one import + registration call here.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies
        sandbox: True for the build sandbox's narrow door (15 October 2026).
            It gets the projects list, the two searches and a
            memory_write_payload that takes only build outcomes which replace
            nothing, off the factory's own shelves; not memory_supersede or
            memory_publish_envelope.
        allowed_projects: one sandbox's own door (17 October 2026), on top of
            ``sandbox``: both searches, the write and memory://projects serve
            only these projects. None serves every project, as before.

    Example (future Wave-3 registrations):
        from fleet_memory.mcp.tools import search_tool, store_tool
        search_tool.register(mcp, context)
        store_tool.register(mcp, context)
    """
    # Register resources
    from fleet_memory.mcp.resources import register_projects_resource

    if allowed_projects is not None and not sandbox:
        raise ValueError("a door bound to projects must also be a sandbox door")

    register_projects_resource(mcp, context, allowed_projects)

    # Wave-3 tool registrations
    from fleet_memory.mcp.tools import search, supersede, write

    search.register(mcp, context, allowed_projects)
    if not sandbox:
        supersede.register(mcp, context)
    write.register(mcp, context, sandbox=sandbox, allowed_projects=allowed_projects)
