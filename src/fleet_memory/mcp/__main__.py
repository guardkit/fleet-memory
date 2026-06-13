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

from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.settings import Settings

# Configure logging to stderr (not stdout, which is used for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Build and run the MCP server over stdio transport.

    Constructs ServerContext with settings, builds the FastMCP server,
    registers tools, and runs over stdio. The server starts even if
    Postgres is unreachable (connection is lazy in the lifespan).
    """
    logger.info("Starting fleet-memory MCP server (stdio transport)")

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

    logger.info("MCP server built, starting stdio transport...")

    # Run the server over stdio
    # This blocks until the client disconnects or the process is killed
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
