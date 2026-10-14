"""memory_publish_envelope: the relay's own ingestion, through the MCP door.

A build sandbox holds no bus password, so a record that only the bus could
carry needs another way in. Prose records (turn states, feature specs and the
other document groups) are published as a ``MemoryEpisodeV1`` envelope with
``content_format`` markdown or text, and the relay chunks them into the store.
The door tool takes exactly that envelope and hands it to the relay's own
``RelayService.ingest``. There is no second storage format and no second
ingestion path.

The proof: the same envelope bytes are ingested twice, once the way the relay
receives them from the bus (``MemoryEpisodeV1`` parsed from the published JSON,
then ``RelayService.ingest``) into one store, and once through the door tool
into another. The two stores must hold identical records: namespaces, keys and
values. LangGraph's in-memory store with the fake embedder stands in for the
database; no database, bus or network is touched.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client
from langgraph.store.memory import InMemoryStore

from fleet_memory.embed import make_fake_embed
from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.relay.chunk_writer import ChunkWriter
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.relay.service import RelayService
from fleet_memory.settings import Settings
from fleet_memory.writer.core import DeterministicWriter

# Small chunks, so a modest body becomes several chunks with overlap.
SETTINGS = Settings.model_construct(chunk_target_tokens=40, chunk_overlap_ratio=0.15)

LONG_MARKDOWN = "\n\n".join(
    f"## Turn {n}\n\n"
    + " ".join(f"The builder changed file_{n}_{w}.py and the reviewer approved it." for w in range(6))
    for n in range(1, 5)
)


def _store() -> InMemoryStore:
    return InMemoryStore(
        index={"dims": 768, "embed": make_fake_embed(dims=768), "fields": ["content"]}
    )


def _published_bytes(**fields: Any) -> bytes:
    """The bytes the publisher puts on the bus: the envelope's JSON."""
    envelope = {
        "episode_id": "document:demo:turn_state_task_1_turn_1",
        "project_id": "demo",
        "episode_type": "document",
        "content_format": "markdown",
        "payload_type": None,
        "body": LONG_MARKDOWN,
        "name": "turn_state TASK-1 turn 1",
        "source": "guardkit",
        "occurred_at": None,
        "published_at": "2026-10-14T12:00:00Z",
        "ingest_hints": None,
        "source_ref": None,
    }
    envelope.update(fields)
    return json.dumps(envelope).encode("utf-8")


async def _relay_path(raw: bytes) -> InMemoryStore:
    """Exactly what the relay does with a message from the bus."""
    store = _store()
    service = RelayService(
        writer=DeterministicWriter(store=store, settings=SETTINGS),
        chunk_writer=ChunkWriter(store=store),
        settings=SETTINGS,
    )
    await service.ingest(MemoryEpisodeV1.model_validate_json(raw))
    return store


async def _door_path(raw: bytes) -> tuple[InMemoryStore, dict[str, Any]]:
    store = _store()
    context = ServerContext(
        store=store, writer=DeterministicWriter(store=store, settings=SETTINGS), settings=SETTINGS
    )
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    async with Client(mcp) as client:
        result = await client.call_tool(
            "memory_publish_envelope", {"envelope": json.loads(raw)}, raise_on_error=False
        )
    text = "".join(getattr(part, "text", "") for part in (result.content or []))
    return store, json.loads(text)


async def _contents(store: InMemoryStore) -> list[tuple[tuple[str, ...], str, Any]]:
    items = await store.asearch(("fleet_memory",), limit=10_000)
    return sorted(
        ((tuple(item.namespace), item.key, item.value) for item in items),
        key=lambda row: (row[0], row[1]),
    )


@pytest.mark.asyncio
async def test_the_tool_is_registered_next_to_the_write_tool() -> None:
    store = _store()
    context = ServerContext(store=store, writer=None, settings=SETTINGS)
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert {"memory_publish_envelope", "memory_write_payload"} <= names


@pytest.mark.asyncio
@pytest.mark.parametrize("content_format", ["markdown", "text"])
async def test_a_prose_envelope_is_stored_exactly_as_the_relay_stores_it(content_format) -> None:
    raw = _published_bytes(content_format=content_format)

    relay_store = await _relay_path(raw)
    door_store, envelope = await _door_path(raw)

    assert envelope["is_error"] is False, envelope
    relay_rows = await _contents(relay_store)
    assert len(relay_rows) > 1, "the body should become several chunks"
    assert all(namespace == ("fleet_memory", "demo", "chunk") for namespace, _, _ in relay_rows)
    assert await _contents(door_store) == relay_rows


@pytest.mark.asyncio
async def test_a_typed_json_envelope_takes_the_relays_typed_path_too() -> None:
    body = {
        "project": "demo",
        "identifier": "TASK_1",
        "source_ref": "FEAT-1",
        "domain_tags": ["task"],
        "status": "success",
        "duration_seconds": 60,
        "lessons": "count with one query",
    }
    raw = _published_bytes(
        episode_id="build_outcome:demo:TASK_1",
        episode_type="build_outcome",
        content_format="json",
        payload_type="build_outcome",
        body=json.dumps(body),
        source_ref="FEAT-1",
    )

    relay_store = await _relay_path(raw)
    door_store, envelope = await _door_path(raw)

    assert envelope["is_error"] is False, envelope
    relay_rows = await _contents(relay_store)
    assert len(relay_rows) == 1
    assert await _contents(door_store) == relay_rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields, words",
    [
        ({"content_format": "pdf"}, "unrecognized content_format"),
        ({"project_id": "not-a-project"}, "invalid"),
        ({"content_format": "json", "payload_type": None}, "missing payload_type"),
    ],
)
async def test_what_the_relay_would_dead_letter_comes_back_as_a_client_error(fields, words) -> None:
    raw = _published_bytes(**fields)

    door_store, envelope = await _door_path(raw)

    assert envelope["is_error"] is True
    assert envelope["error_type"] == "client"
    assert words in envelope["message"]
    assert await _contents(door_store) == []


@pytest.mark.asyncio
async def test_an_envelope_missing_a_required_field_is_refused() -> None:
    envelope = json.loads(_published_bytes())
    del envelope["episode_type"]

    door_store, answer = await _door_path(json.dumps(envelope).encode("utf-8"))

    assert answer["is_error"] is True
    assert answer["error_type"] == "client"
    assert "episode_type" in answer["message"]
    assert await _contents(door_store) == []


@pytest.mark.asyncio
async def test_no_store_is_an_infrastructure_error() -> None:
    context = ServerContext(store=None, writer=None, settings=SETTINGS)
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    async with Client(mcp) as client:
        result = await client.call_tool(
            "memory_publish_envelope",
            {"envelope": json.loads(_published_bytes())},
            raise_on_error=False,
        )
    answer = json.loads("".join(getattr(p, "text", "") for p in result.content))
    assert answer["is_error"] is True
    assert answer["error_type"] == "infrastructure"
