"""The resident http service refuses Host names that are not on its list.

fastmcp ignores an allowed-hosts list unless host/origin protection is on, and
it is off by default, so for a while every Host and Origin was served. These
tests build the real app with the same options main() passes to ``mcp.run`` and
send a real MCP ``initialize`` request through it.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from fleet_memory.mcp.__main__ import http_guard_options, main
from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.settings import Settings

# The names clients really use: estate containers, a session on another machine
# by address, and the default URL in the specialist-agent and guardkit clients.
ALLOWED = ["memory:8005", "host.docker.internal:8005", "10.0.0.1:31822"]

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "host-check-test", "version": "0"},
    },
}


def _settings(allowed: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://user:pw@db.invalid:5432/x")
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.invalid:8000")
    monkeypatch.setenv("FLEET_MEMORY_MCP_TRANSPORT", "http")
    monkeypatch.setenv("FLEET_MEMORY_MCP_ALLOWED_HOSTS", allowed)
    return Settings()


async def _initialize_status(guard: dict[str, Any], host: str, origin: str | None = None) -> int:
    # Settings=None keeps the lifespan from touching Postgres; the guard under
    # test sits in front of the MCP endpoint either way.
    context = ServerContext(store=None, writer=None, settings=None)
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    app = mcp.http_app(transport="http", **guard)

    headers = {
        "Host": host,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if origin is not None:
        headers["Origin"] = origin

    async with app.router.lifespan_context(app):
        # The base URL's own host is unspecified (0.0.0.0) so the guard does not
        # add it to the list, as with the real service bound to 0.0.0.0.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://0.0.0.0") as client:
            response = await client.post("/mcp", json=INITIALIZE, headers=headers)
    return response.status_code


def test_guard_switches_protection_on_when_hosts_are_listed(monkeypatch):
    guard = http_guard_options(_settings(",".join(ALLOWED), monkeypatch))
    assert guard == {"allowed_hosts": ALLOWED, "host_origin_protection": True}


def test_no_list_keeps_todays_behaviour(monkeypatch):
    guard = http_guard_options(_settings(" , ", monkeypatch))
    assert guard == {"allowed_hosts": None}


@pytest.mark.parametrize("host", ALLOWED)
async def test_each_listed_host_is_served(monkeypatch, host):
    guard = http_guard_options(_settings(",".join(ALLOWED), monkeypatch))
    assert await _initialize_status(guard, host) == 200


async def test_localhost_is_served(monkeypatch):
    guard = http_guard_options(_settings(",".join(ALLOWED), monkeypatch))
    assert await _initialize_status(guard, "localhost") == 200


async def test_unknown_host_is_refused(monkeypatch):
    guard = http_guard_options(_settings(",".join(ALLOWED), monkeypatch))
    assert await _initialize_status(guard, "evil.example.com") == 421


async def test_foreign_origin_is_refused(monkeypatch):
    guard = http_guard_options(_settings(",".join(ALLOWED), monkeypatch))
    status = await _initialize_status(guard, "memory:8005", origin="http://evil.example.com")
    assert status == 403


async def test_without_a_list_unknown_hosts_are_still_served(monkeypatch):
    """Documents the kept behaviour: no list configured means no host check."""
    guard = http_guard_options(_settings("", monkeypatch))
    assert await _initialize_status(guard, "evil.example.com") == 200


def test_main_passes_the_guard_to_run(monkeypatch):
    """main() hands mcp.run exactly the options the tests above exercise."""
    from fastmcp import FastMCP

    _settings(",".join(ALLOWED), monkeypatch)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: calls.append(kwargs))

    main()

    assert len(calls) == 1
    assert calls[0]["transport"] == "http"
    assert calls[0]["allowed_hosts"] == ALLOWED
    assert calls[0]["host_origin_protection"] is True
