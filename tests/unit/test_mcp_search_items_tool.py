"""memory_search_items: the ranked results themselves, through the MCP door.

``memory_search`` returns one assembled block, which suits a person reading it
but not a client that scores and filters each result on its own. A build
sandbox that holds no database address reads memory through this door
instead, so the door has to give back the individual results: each one's
natural key, content and score, in ranked order, exactly as the library's own
``retrieval.core.search`` ranks them.

These tests run the real server registration and the real search over
LangGraph's in-memory store with the fake embedder, and call the tool through
an in-process MCP client. No database or network is touched.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client
from langgraph.store.memory import InMemoryStore

from fleet_memory.embed import make_fake_embed
from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
from fleet_memory.mcp.tools.write import memory_write_payload
from fleet_memory.retrieval import SearchRequest, search
from fleet_memory.writer.core import DeterministicWriter

PROJECT = "demo"


def _outcome(identifier: str, lessons: str | None, approach: str | None) -> dict[str, Any]:
    return {
        "payload_type": "build_outcome",
        "project": PROJECT,
        "identifier": identifier,
        "source_ref": f"build:{identifier}",
        "status": "success",
        "duration_seconds": 60,
        "lessons": lessons,
        "approach": approach,
        "domain_tags": ["outcomes"],
    }


def _document(identifier: str, content: str | None) -> dict[str, Any]:
    return {
        "payload_type": "document",
        "project": PROJECT,
        "identifier": identifier,
        "source_ref": f"docs/{identifier}.md",
        "content": content,
        "domain_tags": ["notes"],
    }


async def _seeded() -> ServerContext:
    store = InMemoryStore(
        index={"dims": 768, "embed": make_fake_embed(dims=768), "fields": ["content"]}
    )
    writer = DeterministicWriter(store, settings=None)
    payloads = [
        _outcome("TASK_1", "retry the database call with a short back-off", "wrap the call"),
        _outcome("TASK_2", "count users per day with one grouped query", None),
        # A status shell: no approach and no lessons, so not substantive.
        _outcome("TASK_3", None, None),
        _document("DOC_1", "How the retry policy works for the database client."),
        # Metadata only: no prose content, so not substantive either.
        _document("DOC_2", None),
    ]
    for payload in payloads:
        written = await memory_write_payload(payload, writer)
        assert written.is_error is False, written.message
    return ServerContext(store=store, writer=writer, settings=None)


def _server(context: ServerContext):
    mcp = create_mcp_server(context)
    register_all(mcp, context)
    return mcp


def _envelope(result: Any) -> dict[str, Any]:
    text = "".join(getattr(part, "text", "") for part in (result.content or []))
    return json.loads(text)


async def _call(context: ServerContext, arguments: dict[str, Any]) -> dict[str, Any]:
    async with Client(_server(context)) as client:
        result = await client.call_tool(
            "memory_search_items", arguments, raise_on_error=False
        )
    return _envelope(result)


def _library_ranking(results) -> list[tuple[str, str, float | None]]:
    return [
        (item.value["natural_key"], item.value["content"], item.score) for item in results
    ]


def _door_ranking(envelope: dict[str, Any]) -> list[tuple[str, str, float | None]]:
    return [
        (item["value"]["natural_key"], item["value"]["content"], item["score"])
        for item in envelope["value"]["items"]
    ]


@pytest.mark.asyncio
async def test_the_tool_is_registered_beside_memory_search() -> None:
    context = await _seeded()
    async with Client(_server(context)) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert "memory_search_items" in names
    assert "memory_search" in names


@pytest.mark.asyncio
async def test_it_returns_the_library_ranking_item_by_item() -> None:
    context = await _seeded()
    expected = _library_ranking(
        await search(
            SearchRequest(project=PROJECT, query="database retry", token_budget=2000),
            context.store,
        )
    )
    assert len(expected) >= 3, "the seeded store should give several results"

    envelope = await _call(context, {"project": PROJECT, "query": "database retry"})

    assert envelope["is_error"] is False
    assert _door_ranking(envelope) == expected
    # Each item carries exactly the two value fields and the score, nothing more.
    for item in envelope["value"]["items"]:
        assert set(item) == {"value", "score"}
        assert set(item["value"]) == {"natural_key", "content"}


@pytest.mark.asyncio
async def test_payload_types_and_domain_tags_narrow_it_as_they_narrow_the_library() -> None:
    context = await _seeded()
    expected = _library_ranking(
        await search(
            SearchRequest(
                project=PROJECT,
                query="retry",
                payload_types=["document"],
                domain_tags=["notes"],
                token_budget=2000,
            ),
            context.store,
        )
    )

    envelope = await _call(
        context,
        {
            "project": PROJECT,
            "query": "retry",
            "payload_types": ["document"],
            "domain_tags": ["notes"],
        },
    )

    assert envelope["is_error"] is False
    assert _door_ranking(envelope) == expected
    assert {key for key, _, _ in expected} == {"document:demo:DOC_1", "document:demo:DOC_2"}


@pytest.mark.asyncio
async def test_require_substantive_drops_the_empty_shells() -> None:
    context = await _seeded()
    request = dict(project=PROJECT, query="retry", token_budget=2000)
    everything = _library_ranking(await search(SearchRequest(**request), context.store))
    substantive = _library_ranking(
        await search(SearchRequest(**request, require_substantive=True), context.store)
    )
    shells = {"build_outcome:demo:TASK_3", "document:demo:DOC_2"}
    assert shells <= {key for key, _, _ in everything}
    assert not shells & {key for key, _, _ in substantive}

    plain = await _call(context, {"project": PROJECT, "query": "retry"})
    narrowed = await _call(
        context, {"project": PROJECT, "query": "retry", "require_substantive": True}
    )

    assert _door_ranking(plain) == everything
    assert _door_ranking(narrowed) == substantive


@pytest.mark.asyncio
async def test_a_bad_project_name_comes_back_as_a_tool_error() -> None:
    context = await _seeded()

    envelope = await _call(context, {"project": "Not-A-Project", "query": "retry"})

    assert envelope["is_error"] is True
    assert envelope["error_type"] == "client"
    assert "underscores only" in envelope["message"]
    assert envelope["value"] is None


@pytest.mark.asyncio
async def test_no_store_comes_back_as_a_tool_error() -> None:
    context = ServerContext(store=None, writer=None, settings=None)

    envelope = await _call(context, {"project": PROJECT, "query": "retry"})

    assert envelope["is_error"] is True
    assert envelope["value"] is None
