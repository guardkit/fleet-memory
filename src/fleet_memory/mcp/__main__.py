"""FastMCP stdio entry point for Claude Desktop.

Builds the MCP server from settings and runs it over stdio transport.
The server starts even when Postgres is unreachable (lazy connection).

Usage:
    python -m fleet_memory.mcp

The server communicates over stdin/stdout following the MCP protocol.
Logs go to stderr to avoid mixing with protocol messages.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any

from fleet_memory.mcp.doors import parse_sandbox_doors
from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.settings import Settings

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Configure logging to stderr (not stdout, which is used for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


def http_guard_options(settings: Settings) -> dict[str, Any]:
    """Host-name checking options for the http transport, shared by main() and tests.

    FLEET_MEMORY_MCP_ALLOWED_HOSTS is a comma-separated list of the Host-header
    values clients use (for example ``memory:8005``). fastmcp only enforces an
    allowed-hosts list when ``host_origin_protection`` is switched on, and it is
    off by default, so passing the list alone accepted every Host and Origin.

    With a list configured, protection is switched on: a listed host is served,
    as are localhost / 127.0.0.1 / ::1 and the address the connection actually
    arrived on, which fastmcp always allows; any other Host gets 421, and a
    browser Origin that is not the request's own host gets 403. fastmcp matches
    the name only; the port in an entry is ignored. Clients using the default
    URL http://host.docker.internal:8005/mcp need host.docker.internal listed.

    With no list configured, today's behaviour is kept on purpose: no list is
    passed and protection is left at fastmcp's own setting (off unless
    FASTMCP_HTTP_HOST_ORIGIN_PROTECTION says otherwise). Switching it on for an
    empty list would refuse every client that reaches the service by a name
    other than localhost, which is how existing deployments without the
    setting are used.
    """
    allowed_hosts = [h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()]
    if not allowed_hosts:
        return {"allowed_hosts": None}
    return {"allowed_hosts": allowed_hosts, "host_origin_protection": True}


def build_servers(settings: Settings) -> tuple[FastMCP, list[tuple[FastMCP, int]]]:
    """The main server, and the sandbox doors with the port each listens on.

    All are built over one ServerContext. Only the main server opens the
    store; the doors' tools read the context at call time, so they use the
    store the main server opened.

    - Neither sandbox setting: only the main server, as before.
    - FLEET_MEMORY_MCP_SANDBOX_PORT: the single narrow door, serving every
      project, exactly as before.
    - FLEET_MEMORY_MCP_SANDBOX_DOORS (17 October 2026): one narrow door per
      entry, each serving only its own projects.

    Raises ValueError when the doors setting is malformed or both are set, so
    the service refuses to start rather than open a door wider than intended.
    """
    doors = parse_sandbox_doors(settings.mcp_sandbox_doors, main_port=settings.mcp_port)
    single_port = settings.mcp_sandbox_port.strip()
    if doors and single_port:
        raise ValueError(
            "set FLEET_MEMORY_MCP_SANDBOX_DOORS or FLEET_MEMORY_MCP_SANDBOX_PORT, not both"
        )
    # Create server context (store and writer are built lazily in lifespan)
    context = ServerContext(store=None, writer=None, settings=settings)
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    served: list[tuple[FastMCP, int]] = []
    if single_port:
        door = create_mcp_server(context, opens_store=False)
        register_all(door, context, sandbox=True)
        served.append((door, int(single_port)))
    for entry in doors:
        door = create_mcp_server(context, opens_store=False)
        register_all(door, context, sandbox=True, allowed_projects=entry.projects)
        served.append((door, entry.port))
    return mcp, served


async def _serve_both(served: list[tuple[FastMCP, int]], host: str, guard: dict[str, Any]) -> None:
    """Run the http servers in one process; when any stops, the process ends.

    A stop by signal reaches each (uvicorn passes the signal on), so the others
    gets a few seconds to finish cleanly before it is cancelled. A failure is
    raised again, so the process exits with an error and Compose restarts it.
    """
    tasks = [
        asyncio.create_task(
            server.run_http_async(
                transport="http", host=host, port=port, show_banner=index == 0, **guard
            )
        )
        for index, (server, port) in enumerate(served)
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    if pending:
        more_done, pending = await asyncio.wait(pending, timeout=5)
        done |= more_done
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()


def main() -> None:
    """Build and run the MCP server.

    Constructs ServerContext with settings, builds the FastMCP server,
    registers tools, and runs over the configured transport — stdio for
    spawned clients (default), http for the resident fleet service
    (FLEET_MEMORY_MCP_TRANSPORT=http). The server starts even if
    Postgres is unreachable (connection is lazy in the lifespan).
    """
    # Load settings from environment
    try:
        settings = Settings()
        logger.info("Settings loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Build the FastMCP server(s) and register their tools
    try:
        mcp, doors = build_servers(settings)
    except ValueError as e:
        logger.error("Refusing to start: %s", e)
        sys.exit(1)

    transport = settings.mcp_transport.strip().lower()
    if transport == "http":
        guard = http_guard_options(settings)
        logger.info(
            "MCP server built, starting http transport on %s:%s (allowed hosts: %s)...",
            settings.mcp_host,
            settings.mcp_port,
            ", ".join(guard["allowed_hosts"]) if guard["allowed_hosts"] else "not checked",
        )
        if doors:
            for _door, port in doors:
                logger.info("and a sandbox's narrow door on %s:%s", settings.mcp_host, port)
            asyncio.run(_serve_both([(mcp, settings.mcp_port), *doors], settings.mcp_host, guard))
            return
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            **guard,
        )
    elif transport == "stdio":
        logger.info("MCP server built, starting stdio transport...")
        # This blocks until the client disconnects or the process is killed
        mcp.run(transport="stdio")
    else:
        logger.error(
            "Unknown FLEET_MEMORY_MCP_TRANSPORT %r (expected 'stdio' or 'http')",
            settings.mcp_transport,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
