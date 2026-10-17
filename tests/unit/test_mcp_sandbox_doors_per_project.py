"""One narrow memory door per build sandbox, each bound to its own projects (17 October 2026).

FLEET_MEMORY_MCP_SANDBOX_DOORS builds one narrow door per entry. Each keeps
the single narrow door's rules and also refuses any search, write or listing
for a project outside its own list, with a plain error that names no project.
Unset, the service behaves exactly as before.

These tests start from the setting and go through the real entry point's
build, the real tool registration and the real search and writer, over
LangGraph's in-memory store with the fake embedder, called through in-process
MCP clients. No database, bus or network is used.
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
from fleet_memory.mcp.doors import DOOR_PROJECT_REFUSAL, parse_sandbox_doors
from fleet_memory.mcp.tools.write import SANDBOX_REFUSAL
from fleet_memory.settings import Settings

DOORS = "8006:proj_a|proj_b,8007:proj_c,8008:guardkit"
NARROW_THREE = {"memory_search", "memory_search_items", "memory_write_payload"}


def _outcome(project: str, identifier: str = "TASK_1", **fields: Any) -> dict[str, Any]:
    payload = {
        "payload_type": "build_outcome",
        "project": project,
        "identifier": identifier,
        "source_ref": "guardkit:autobuild",
        "status": "success",
        "duration_seconds": 12,
        "lessons": f"private marker for {project}: the tests needed the fixture",
    }
    payload.update(fields)
    return payload


def _settings(monkeypatch: pytest.MonkeyPatch, *, doors: str = "", port: str = "") -> Settings:
    monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://user:pw@db.invalid:5432/x")
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.invalid:8000")
    monkeypatch.setenv("FLEET_MEMORY_MCP_TRANSPORT", "http")
    monkeypatch.setenv("FLEET_MEMORY_MCP_ALLOWED_HOSTS", "")
    monkeypatch.setenv("FLEET_MEMORY_MCP_SANDBOX_PORT", port)
    monkeypatch.setenv("FLEET_MEMORY_MCP_SANDBOX_DOORS", doors)
    return Settings()


def _text(result: Any) -> str:
    return "".join(getattr(part, "text", "") for part in (result.content or []))


class Estate:
    """The main server and its doors over one in-memory store, seeded through the main server."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, doors: str = "", port: str = "") -> None:
        self.store = InMemoryStore(
            index={"dims": 768, "embed": make_fake_embed(dims=768), "fields": ["content"]}
        )

        @asynccontextmanager
        async def stand_in_store_context(_settings: Settings):
            yield self.store

        monkeypatch.setattr("fleet_memory.store.async_store_context", stand_in_store_context)
        self.main, served = entry.build_servers(_settings(monkeypatch, doors=doors, port=port))
        self.doors: dict[int, FastMCP] = {p: door for door, p in served}
        self.ports = [p for _, p in served]

    async def run(self, port: int, steps):
        """Run ``steps(door_client)`` with the main server up and seeded with three projects."""
        async with Client(self.main) as main_client:
            for project in ("proj_a", "proj_b", "proj_c"):
                written = await main_client.call_tool(
                    "memory_write_payload", {"payload": _outcome(project)}, raise_on_error=False
                )
                assert json.loads(_text(written))["is_error"] is False, _text(written)
            async with Client(self.doors[port]) as door_client:
                return await steps(door_client)

    async def keys(self, project: str) -> list[str]:
        stored = await self.store.asearch(("fleet_memory", project, "build_outcome"), limit=100)
        return sorted(item.value["natural_key"] for item in stored)


async def _call(client: Client, tool: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
    result = await client.call_tool(tool, arguments, raise_on_error=False)
    text = _text(result)
    return json.loads(text), text


def _assert_door_refused(envelope: dict[str, Any], text: str) -> None:
    assert envelope["is_error"] is True, envelope
    assert envelope["error_type"] == "client"
    assert envelope["message"] == DOOR_PROJECT_REFUSAL
    for name in ("proj_a", "proj_b", "proj_c", "guardkit"):
        assert name not in text, text


# --- searches ------------------------------------------------------------------


@pytest.mark.parametrize("tool", ["memory_search", "memory_search_items"])
async def test_a_door_searches_its_own_projects(monkeypatch, tool) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return [
            await _call(client, tool, {"project": project, "query": "private marker"})
            for project in ("proj_a", "proj_b")
        ]

    for (envelope, text), project in zip(await estate.run(8006, steps), ("proj_a", "proj_b")):
        assert envelope["is_error"] is False, envelope
        assert f"private marker for {project}" in text
        assert "proj_c" not in text


@pytest.mark.parametrize("tool", ["memory_search", "memory_search_items"])
@pytest.mark.parametrize(
    ("port", "project"),
    [(8007, "proj_a"), (8007, "proj_b"), (8006, "proj_c"), (8007, "guardkit"), (8007, "")],
)
async def test_a_door_refuses_a_search_outside_its_projects(
    monkeypatch, tool, port, project
) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return await _call(client, tool, {"project": project, "query": "private marker"})

    _assert_door_refused(*await estate.run(port, steps))


@pytest.mark.parametrize("tool", ["memory_search", "memory_search_items"])
async def test_a_door_refuses_a_search_with_no_project(monkeypatch, tool) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        result = await client.call_tool(tool, {"query": "fixture"}, raise_on_error=False)
        return result, _text(result)

    result, text = await estate.run(8007, steps)
    assert result.is_error is True, text
    assert "private marker" not in text


# --- writes --------------------------------------------------------------------


async def test_a_door_for_proj_c_cannot_write_for_proj_a(monkeypatch) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return await _call(client, "memory_write_payload", {"payload": _outcome("proj_a", "T2")})

    _assert_door_refused(*await estate.run(8007, steps))
    assert await estate.keys("proj_a") == ["build_outcome:proj_a:TASK_1"]


async def test_a_door_writes_a_build_outcome_for_its_own_project(monkeypatch) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return await _call(client, "memory_write_payload", {"payload": _outcome("proj_c", "T2")})

    envelope, _ = await estate.run(8007, steps)
    assert envelope["is_error"] is False, envelope
    assert envelope["value"] == "build_outcome:proj_c:T2"
    assert await estate.keys("proj_c") == ["build_outcome:proj_c:T2", "build_outcome:proj_c:TASK_1"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {
                "payload_type": "adr",
                "project": "proj_c",
                "identifier": "ADR_1",
                "source_ref": "github:org/repo@abc123",
                "decision": "Use PostgreSQL",
                "status": "accepted",
            },
            id="adr-on-its-own-project",
        ),
        pytest.param(
            _outcome("proj_c", "T2", supersedes=["build_outcome:proj_c:TASK_1"]),
            id="replacement-on-its-own-project",
        ),
    ],
)
async def test_the_narrow_doors_rules_still_hold_on_a_project_door(monkeypatch, payload) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return await _call(client, "memory_write_payload", {"payload": payload})

    envelope, _ = await estate.run(8007, steps)
    assert envelope["is_error"] is True and envelope["message"] == SANDBOX_REFUSAL, envelope
    assert await estate.keys("proj_c") == ["build_outcome:proj_c:TASK_1"]


async def test_a_door_listing_a_factory_shelf_still_cannot_write_on_it(monkeypatch) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return await _call(client, "memory_write_payload", {"payload": _outcome("guardkit")})

    envelope, _ = await estate.run(8008, steps)
    assert envelope["is_error"] is True and envelope["message"] == SANDBOX_REFUSAL, envelope
    assert await estate.keys("guardkit") == []


# --- listings and the whole surface --------------------------------------------


@pytest.mark.parametrize(
    ("port", "expected"), [(8006, ["proj_a", "proj_b"]), (8007, ["proj_c"]), (8008, [])]
)
async def test_a_door_lists_only_its_own_projects(monkeypatch, port, expected) -> None:
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return await client.read_resource("memory://projects")

    contents = await estate.run(port, steps)
    assert json.loads(contents[0].text) == expected


async def test_the_main_server_still_lists_every_project(monkeypatch) -> None:
    estate = Estate(monkeypatch, doors=DOORS)
    async with Client(estate.main) as client:
        await client.call_tool("memory_write_payload", {"payload": _outcome("proj_a")})
        await client.call_tool("memory_write_payload", {"payload": _outcome("proj_c")})
        contents = await client.read_resource("memory://projects")
    assert json.loads(contents[0].text) == ["proj_a", "proj_c"]


async def test_a_door_offers_nothing_beyond_the_checked_tools_and_listing(monkeypatch) -> None:
    # Anything registered on a door later must be checked against the door's
    # projects; this fails first so that check is not forgotten.
    estate = Estate(monkeypatch, doors=DOORS)

    async def steps(client: Client):
        return (
            {tool.name for tool in await client.list_tools()},
            {str(resource.uri) for resource in await client.list_resources()},
            await client.list_resource_templates(),
            await client.list_prompts(),
        )

    tools, resources, templates, prompts = await estate.run(8007, steps)
    assert tools == NARROW_THREE
    assert resources == {"memory://projects"}
    assert templates == []
    assert prompts == []


# --- the setting ---------------------------------------------------------------


def test_each_entry_becomes_a_door_on_its_own_port(monkeypatch) -> None:
    assert Estate(monkeypatch, doors=DOORS).ports == [8006, 8007, 8008]
    assert parse_sandbox_doors(" 8006 : proj_a | proj_b ", main_port=8005)[0].projects == {
        "proj_a",
        "proj_b",
    }


def test_main_serves_every_door_in_one_process(monkeypatch) -> None:
    _settings(monkeypatch, doors=DOORS)
    http_ports: list[int] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: pytest.fail("ran one server"))

    async def run_http_async(self: FastMCP, **kwargs: Any) -> None:
        http_ports.append(kwargs["port"])

    monkeypatch.setattr(FastMCP, "run_http_async", run_http_async)
    entry.main()
    assert http_ports == [8005, 8006, 8007, 8008]


async def test_unset_keeps_the_single_door_serving_every_project(monkeypatch) -> None:
    estate = Estate(monkeypatch, port="8006")
    assert estate.ports == [8006]

    async def steps(client: Client):
        found = [
            await _call(client, "memory_search_items", {"project": p, "query": "private marker"})
            for p in ("proj_a", "proj_c")
        ]
        written = await _call(client, "memory_write_payload", {"payload": _outcome("proj_a", "T2")})
        listing = await client.read_resource("memory://projects")
        return found, written, listing

    found, (written, _), listing = await estate.run(8006, steps)
    assert [envelope["is_error"] for envelope, _ in found] == [False, False]
    assert "private marker for proj_c" in found[1][1]
    assert written["is_error"] is False, written
    assert json.loads(listing[0].text) == ["proj_a", "proj_b", "proj_c"]


def test_unset_with_no_sandbox_port_builds_no_door(monkeypatch) -> None:
    assert Estate(monkeypatch).ports == []


@pytest.mark.parametrize(
    "value",
    [
        "8006",
        "8006:",
        ":proj_a",
        "door:proj_a",
        "0:proj_a",
        "70000:proj_a",
        "٨٠٠٦:proj_a",
        "8005:proj_a",
        "8006:proj_a,8006:proj_b",
        "8006:proj_a,8007:proj_a",
        "8006:proj_a|proj_a",
        "8006:Proj_A",
        "8006:proj-a",
        "8006:proj_a|",
        "8006:proj_a,",
    ],
)
def test_a_malformed_setting_refuses_to_start(monkeypatch, value) -> None:
    settings = _settings(monkeypatch, doors=value)
    with pytest.raises(ValueError, match="FLEET_MEMORY_MCP_SANDBOX_DOORS"):
        entry.build_servers(settings)
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: pytest.fail("started"))
    with pytest.raises(SystemExit) as stopped:
        entry.main()
    assert stopped.value.code == 1


def test_both_settings_at_once_refuse_to_start(monkeypatch) -> None:
    settings = _settings(monkeypatch, doors="8007:proj_c", port="8006")
    with pytest.raises(ValueError, match="not both"):
        entry.build_servers(settings)
