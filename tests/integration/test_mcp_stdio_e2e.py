"""End-to-end integration tests for the fleet-memory MCP server.

Rewritten 2026-08-03 (memory reconnection): the original file spoke raw
JSON-RPC to the subprocess without an MCP initialize handshake and set env
keys (FLEET_MEMORY_DATABASE_URL) that predate the Settings shape — it was
deselected by default and never ran against a real server. These tests use
the fastmcp Client so every assertion goes through the actual MCP protocol.

Covers the three seams the 2026-08-03 audit found broken:
- lifespan contract (fastmcp 3.x passes the server instance)
- tool access to dependencies (shared ServerContext, not mcp.get_state())
- canonical tool names (memory_search / memory_write_payload /
  memory_supersede — the names every guardkit command spec selects)

Marked @pytest.mark.integration (deselected by default; run with
`pytest -m integration`).
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from fastmcp import Client

from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all

CANONICAL_TOOLS = {"memory_search", "memory_write_payload", "memory_supersede"}


def _build_degraded_server() -> Any:
    """Build a server in degraded mode (no settings, no store, no writer)."""
    context = ServerContext(store=None, writer=None, settings=None)
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    return mcp


@pytest.mark.integration
async def test_tools_advertised_under_canonical_names() -> None:
    """The server advertises exactly the canonical tool names.

    These are the names the installed guardkit command specs select
    (mcp__fleet_memory__memory_search etc.) — the 2026-08-03 audit found
    the server minting *_tool-suffixed names nothing selects.
    """
    mcp = _build_degraded_server()

    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert CANONICAL_TOOLS <= names, f"missing canonical tools: {CANONICAL_TOOLS - names}"
        # The stale *_tool names must NOT be advertised alongside them
        assert not any(n.endswith("_tool") for n in names), names


@pytest.mark.integration
async def test_projects_resource_advertised() -> None:
    """The memory://projects resource is registered."""
    mcp = _build_degraded_server()

    async with Client(mcp) as client:
        resources = await client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "memory://projects" in uris, uris


@pytest.mark.integration
async def test_tool_calls_degrade_without_crashing() -> None:
    """All three tools return structured errors (not crashes) in degraded mode.

    This exercises the full protocol call path through the shared
    ServerContext seam — the path that crashed with AttributeError under
    the old mcp.get_state() wiring on every real call.
    """
    mcp = _build_degraded_server()

    async with Client(mcp) as client:
        search = await client.call_tool(
            "memory_search", {"project": "guardkit", "query": "anything"}
        )
        # tool_safe maps the missing store to a client/infrastructure envelope
        assert search.data is not None
        assert search.data.get("is_error") is True

        write = await client.call_tool(
            "memory_write_payload", {"payload": {"payload_type": "adr"}}
        )
        assert write.data is not None
        assert write.data.get("is_error") is True
        assert write.data.get("error_type") == "infrastructure"

        supersede = await client.call_tool(
            "memory_supersede",
            {"successor_key": "adr:p:A2", "predecessor_keys": ["adr:p:A1"]},
        )
        assert supersede.data is not None
        assert supersede.data.get("is_error") is True
        assert supersede.data.get("error_type") == "infrastructure"


@pytest.mark.integration
async def test_server_boots_over_stdio_with_unreachable_store() -> None:
    """A spawned stdio server completes the MCP handshake with Postgres down.

    Uses the real Settings env contract (FLEET_MEMORY_PG_DSN /
    FLEET_MEMORY_EMBED_URL). The store connection is lazy, so an
    unreachable DSN must not prevent startup or tool listing.
    """
    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "fleet_memory.mcp"],
        env={
            "FLEET_MEMORY_PG_DSN": "postgresql://invalid:invalid@127.0.0.1:1/nonexistent",
            "FLEET_MEMORY_EMBED_URL": "http://127.0.0.1:1/v1",
            "FLEET_MEMORY_MCP_TRANSPORT": "stdio",
        },
    )

    async with Client(transport) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert CANONICAL_TOOLS <= names, f"missing canonical tools: {CANONICAL_TOOLS - names}"
