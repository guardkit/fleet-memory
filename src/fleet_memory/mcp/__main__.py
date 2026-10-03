"""FastMCP stdio entry point for Claude Desktop.

Builds the MCP server from settings and runs it over stdio transport.
The server starts even when Postgres is unreachable (lazy connection).

Usage:
    python -m fleet_memory.mcp

The server communicates over stdin/stdout following the MCP protocol.
Logs go to stderr to avoid mixing with protocol messages.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.settings import Settings

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

    # Create server context (store and writer are built lazily in lifespan)
    context = ServerContext(store=None, writer=None, settings=settings)

    # Build the FastMCP server
    mcp = create_mcp_server(context)

    # Register all tools (Wave-1: no-op, Wave-3: adds tools)
    register_all(mcp, context)

    transport = settings.mcp_transport.strip().lower()
    if transport == "http":
        guard = http_guard_options(settings)
        logger.info(
            "MCP server built, starting http transport on %s:%s (allowed hosts: %s)...",
            settings.mcp_host,
            settings.mcp_port,
            ", ".join(guard["allowed_hosts"]) if guard["allowed_hosts"] else "not checked",
        )
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
