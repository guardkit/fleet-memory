"""Unit tests for FastMCP server scaffolding.

Tests that the MCP server can be built without a store connection,
and that the stdio entrypoint is importable.
"""

from __future__ import annotations

import pytest


def test_server_builds_without_store() -> None:
    """Build the server with a fake/None store; assert it constructs.

    The server must start even when Postgres is unreachable at launch.
    This test verifies that create_mcp_server can be called with a
    ServerContext that has None/fake dependencies.
    """
    from fleet_memory.mcp.server import ServerContext, create_mcp_server

    # Create a fake context with None store (degraded mode)
    context = ServerContext(store=None, writer=None, settings=None)

    # Should construct without errors
    mcp = create_mcp_server(context)

    # Verify it's a FastMCP instance
    # We check for the run method as a signature of FastMCP
    assert hasattr(mcp, "run"), "Expected FastMCP instance with run() method"


def test_stdio_entrypoint_importable() -> None:
    """Verify that the __main__.py entrypoint can be imported without errors.

    This doesn't run the server, just checks that the module loads cleanly.
    """
    # Should not raise any import errors
    import fleet_memory.mcp.__main__  # noqa: F401


@pytest.mark.asyncio
async def test_register_all_is_no_op_without_tools() -> None:
    """Verify that register_all is a no-op when no tool modules are present.

    Wave-3 tasks will add tool registrations, but for now register_all
    should be callable and do nothing.
    """
    from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all

    context = ServerContext(store=None, writer=None, settings=None)
    mcp = create_mcp_server(context)

    # Should not raise errors
    register_all(mcp, context)

    # No assertions needed - just checking it doesn't crash
