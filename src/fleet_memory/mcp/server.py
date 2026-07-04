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


def create_mcp_server(context: ServerContext) -> FastMCP:
    """Create a FastMCP server instance with the given context.

    Builds a FastMCP server configured for stdio transport. The server
    is constructed immediately, but connection to the store is deferred
    until the lifespan context manager is entered (lazy initialization).

    Args:
        context: ServerContext with dependencies (can have None values)

    Returns:
        Configured FastMCP instance ready to run over stdio
    """

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[dict[str, Any]]:
        """Lifespan context manager: lazy store initialization.

        Entry:
            - If context has a settings instance, builds store + writer
            - Yields a state dict with dependencies for tools
            - Degraded mode (context.store=None): yields empty state

        Exit:
            - Closes store connection pool cleanly (if opened)

        Yields:
            State dict with 'store', 'writer', 'settings' keys
        """
        # Degraded/test mode: context has None dependencies
        # Yield empty state and skip store initialization
        if context.settings is None or context.store is not None:
            # Test mode: use the provided context directly
            yield {
                "store": context.store,
                "writer": context.writer,
                "settings": context.settings,
            }
            return

        # Production mode: lazy store initialization
        # Import store context manager from existing infrastructure
        from fleet_memory.store import async_store_context
        from fleet_memory.writer.core import DeterministicWriter

        # Enter store context (connects to Postgres, sets up embed callable)
        async with async_store_context(context.settings) as store:
            # Build writer with the connected store
            writer = DeterministicWriter(store=store, settings=context.settings)

            # Yield state for tools to access
            yield {
                "store": store,
                "writer": writer,
                "settings": context.settings,
            }

            # Exit: async_store_context closes pool automatically

    # Create FastMCP instance with lifespan
    # Name identifies this server in MCP client logs
    mcp = FastMCP("fleet-memory", lifespan=lifespan)

    return mcp


def register_all(mcp: FastMCP, context: ServerContext) -> None:
    """Register all MCP tools and resources on the given server instance.

    Extension point for Wave-3 tool registration tasks. Each tool task
    will add one import + registration call here.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies

    Example (future Wave-3 registrations):
        from fleet_memory.mcp.tools import search_tool, store_tool
        search_tool.register(mcp, context)
        store_tool.register(mcp, context)
    """
    # Register resources
    from fleet_memory.mcp.resources import register_projects_resource

    register_projects_resource(mcp, context)

    # Wave-3 tool registrations
    from fleet_memory.mcp.tools import search, supersede, write

    search.register(mcp, context)
    supersede.register(mcp, context)
    write.register(mcp, context)
