"""The build sandbox's narrow memory door (15 October 2026).

Code in a build can reach the sandbox's door, so that door offers only the two
searches and a write that takes nothing but build outcomes which replace
nothing, and never on the factory's or its agents' own shelves. The Dell's own
tools keep the full door, with all five tools. Both doors run in one process
over one store, which only the main server opens.

A stand-in writer records what reaches it; LangGraph's in-memory store with the
fake embedder stands in for the database. No database, bus or network is used.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from langgraph.store.memory import InMemoryStore

from fleet_memory.embed import make_fake_embed
from fleet_memory.mcp import __main__ as entry
from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.mcp.tools.write import RESERVED_PROJECTS
from fleet_memory.settings import Settings

ALL_FIVE = {
    "memory_search",
    "memory_search_items",
    "memory_write_payload",
    "memory_publish_envelope",
    "memory_supersede",
}
NARROW_THREE = {"memory_search", "memory_search_items", "memory_write_payload"}


class StandInWriter:
    def __init__(self) -> None:
        self.writes: list[Any] = []

    async def write(self, payload: Any) -> None:
        self.writes.append(payload)


def _build_outcome(project: str = "some_product", **fields: Any) -> dict[str, Any]:
    payload = {
        "payload_type": "build_outcome",
        "project": project,
        "identifier": "TASK_1",
        "source_ref": "guardkit:autobuild",
        "status": "success",
        "duration_seconds": 12,
        "lessons": "the tests needed the fixture",
    }
    payload.update(fields)
    return payload


def _adr(project: str = "some_product") -> dict[str, Any]:
    return {
        "payload_type": "adr",
        "project": project,
        "identifier": "ADR_1",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL",
        "status": "accepted",
    }


def _document(project: str = "some_product") -> dict[str, Any]:
    return {
        "payload_type": "document",
        "project": project,
        "identifier": "DOC_1",
        "source_ref": "github:org/repo@abc123",
        "content": "Accepted architecture: everything is fine.",
    }


def _server(writer: StandInWriter, *, sandbox: bool) -> FastMCP:
    context = ServerContext(store=None, writer=writer, settings=None)  # type: ignore[arg-type]
    mcp = create_mcp_server(context, opens_store=not sandbox)
    register_all(mcp, context, sandbox=sandbox)
    return mcp


async def _tool_names(mcp: FastMCP) -> set[str]:
    async with Client(mcp) as client:
        return {tool.name for tool in await client.list_tools()}


async def _write(mcp: FastMCP, payload: dict[str, Any]) -> dict[str, Any]:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "memory_write_payload", {"payload": payload}, raise_on_error=False
        )
    return json.loads("".join(getattr(part, "text", "") for part in (result.content or [])))


def _assert_refused(result: dict[str, Any], writer: StandInWriter) -> None:
    assert result["is_error"] is True, result
    assert result["error_type"] == "client"
    assert result["message"].startswith(
        "the sandbox's memory door accepts only build outcomes that replace nothing"
    )
    assert writer.writes == []


# --- what the narrow door offers --------------------------------------------


async def test_the_narrow_door_lists_the_two_searches_and_the_write() -> None:
    assert await _tool_names(_server(StandInWriter(), sandbox=True)) == NARROW_THREE


async def test_the_main_door_still_lists_all_five_tools() -> None:
    assert await _tool_names(_server(StandInWriter(), sandbox=False)) == ALL_FIVE


# --- what the narrow door accepts and refuses -------------------------------


async def test_a_build_outcome_on_an_ordinary_shelf_reaches_the_writer() -> None:
    writer = StandInWriter()
    result = await _write(_server(writer, sandbox=True), _build_outcome("some_product"))
    assert result["is_error"] is False, result
    assert result["value"] == "build_outcome:some_product:TASK_1"
    assert [payload.natural_key for payload in writer.writes] == [
        "build_outcome:some_product:TASK_1"
    ]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_adr(), id="adr"),
        pytest.param(_document(), id="document"),
        pytest.param(
            _build_outcome(supersedes=["build_outcome:some_product:TASK_0"]),
            id="build_outcome-with-supersedes",
        ),
    ],
)
async def test_the_narrow_door_refuses_other_kinds_and_replacements(payload) -> None:
    writer = StandInWriter()
    _assert_refused(await _write(_server(writer, sandbox=True), payload), writer)


@pytest.mark.parametrize("project", [*RESERVED_PROJECTS, "GuardKit"])
async def test_the_narrow_door_refuses_the_factorys_own_shelves(project) -> None:
    writer = StandInWriter()
    _assert_refused(await _write(_server(writer, sandbox=True), _build_outcome(project)), writer)


@pytest.mark.parametrize("project", ["guardkit\n", "some_product\n"])
async def test_a_shelf_name_with_a_trailing_newline_is_refused(project) -> None:
    # A final newline once slipped past the name check ("$" matches before it) and
    # landed the record on a shelf of its own (coach note, 15 October 2026).
    writer = StandInWriter()
    result = await _write(_server(writer, sandbox=True), _build_outcome(project))
    assert result["is_error"] is True, result
    assert writer.writes == []


def test_the_reserved_shelves_are_the_designs_ten() -> None:
    assert RESERVED_PROJECTS == (
        "guardkit",
        "guardkitfactory",
        "forge",
        "fleet_memory",
        "nats_core",
        "specialist_agent",
        "jarvis",
        "office_manager",
        "ai_transition",
        "software_factory",
    )


async def test_the_main_door_still_accepts_an_adr_on_guardkit() -> None:
    writer = StandInWriter()
    result = await _write(_server(writer, sandbox=False), _adr("guardkit"))
    assert result["is_error"] is False, result
    assert [payload.natural_key for payload in writer.writes] == ["adr:guardkit:ADR_1"]


# --- one process, one context, one store ------------------------------------


def _settings(monkeypatch: pytest.MonkeyPatch, sandbox_port: str) -> Settings:
    monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://user:pw@db.invalid:5432/x")
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.invalid:8000")
    monkeypatch.setenv("FLEET_MEMORY_MCP_TRANSPORT", "http")
    monkeypatch.setenv("FLEET_MEMORY_MCP_ALLOWED_HOSTS", "")
    monkeypatch.setenv("FLEET_MEMORY_MCP_SANDBOX_PORT", sandbox_port)
    monkeypatch.delenv("FLEET_MEMORY_MCP_SANDBOX_DOORS", raising=False)
    return Settings()


def _record_runs(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[Any]]:
    runs: list[Any] = []
    http_runs: list[Any] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: runs.append((self, kwargs)))

    async def run_http_async(self: FastMCP, **kwargs: Any) -> None:
        http_runs.append((self, kwargs))

    monkeypatch.setattr(FastMCP, "run_http_async", run_http_async)
    return runs, http_runs


def test_with_no_sandbox_port_only_one_server_is_built(monkeypatch) -> None:
    settings = _settings(monkeypatch, "")
    mcp, doors = entry.build_servers(settings)
    assert doors == []

    runs, http_runs = _record_runs(monkeypatch)
    entry.main()
    assert len(runs) == 1
    assert runs[0][1]["port"] == 8005
    assert http_runs == []


def test_with_a_sandbox_port_both_servers_run_on_their_own_ports(monkeypatch) -> None:
    _settings(monkeypatch, "8006")
    runs, http_runs = _record_runs(monkeypatch)
    entry.main()
    assert runs == []
    assert [kwargs["port"] for _, kwargs in http_runs] == [8005, 8006]
    assert http_runs[0][0] is not http_runs[1][0]


async def test_both_servers_share_one_store_which_only_the_main_server_opens(monkeypatch) -> None:
    store = InMemoryStore(
        index={"dims": 768, "embed": make_fake_embed(dims=768), "fields": ["content"]}
    )
    opened: list[InMemoryStore] = []

    @asynccontextmanager
    async def stand_in_store_context(_settings: Settings):
        opened.append(store)
        yield store

    monkeypatch.setattr("fleet_memory.store.async_store_context", stand_in_store_context)
    mcp, [(door, port)] = entry.build_servers(_settings(monkeypatch, "8006"))
    assert port == 8006

    # The narrow door starts first here, as it may in the real process: it
    # must not open a store of its own, and it must see the main server's.
    async with Client(door) as door_client:
        assert opened == [], "the narrow door must not open a store"
        async with Client(mcp) as main_client:
            assert opened == [store]
            result = await door_client.call_tool(
                "memory_write_payload", {"payload": _build_outcome()}, raise_on_error=False
            )
            names = {tool.name for tool in await main_client.list_tools()}

    text = "".join(getattr(part, "text", "") for part in (result.content or []))
    assert json.loads(text)["is_error"] is False, text
    assert names == ALL_FIVE
    stored = await store.asearch(("fleet_memory", "some_product", "build_outcome"), limit=100)
    assert [item.value["natural_key"] for item in stored] == ["build_outcome:some_product:TASK_1"]
