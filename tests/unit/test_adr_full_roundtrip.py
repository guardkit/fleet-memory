"""A full ADR written through memory_write_payload comes back through memory_search.

Uses the real DeterministicWriter and the real search over LangGraph's InMemoryStore with the
fake embedder, so no database or network is needed. The ADR's title, context, consequences and
alternatives must survive the write and appear in the retrieved context.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langgraph.store.memory import InMemoryStore

from fleet_memory.embed import make_fake_embed
from fleet_memory.mcp.tools.search import memory_search
from fleet_memory.mcp.tools.write import memory_write_payload
from fleet_memory.writer.core import DeterministicWriter


@pytest.mark.asyncio
async def test_full_adr_round_trips_through_write_and_search() -> None:
    store = InMemoryStore(index={"dims": 768, "embed": make_fake_embed(dims=768), "fields": ["content"]})
    writer = DeterministicWriter(store, settings=None)
    payload = {
        "payload_type": "adr",
        "project": "demo",
        "identifier": "ADR_ARCH_001",
        "source_ref": "docs/architecture/decisions/ADR-ARCH-001-api.md",
        "title": "FastAPI for the API",
        "decision": "Use FastAPI for the HTTP API",
        "status": "accepted",
        "context": "The agent is Python and the API must validate input.",
        "consequences": "One language across agent and API.",
        "alternatives": ["Flask", "Django REST framework"],
        "domain_tags": ["architecture"],
    }

    written = await memory_write_payload(payload, writer)
    assert written.is_error is False
    assert written.value == "adr:demo:ADR_ARCH_001"

    found = await memory_search(
        project="demo",
        query="why FastAPI",
        payload_types=["adr"],
        domain_tags=["architecture"],
        context=SimpleNamespace(store=store, writer=writer, settings=None),
    )
    assert found.is_error is False
    record = json.loads(found.value["context_block"])
    assert record["title"] == "FastAPI for the API"
    assert record["context"].startswith("The agent is Python")
    assert record["consequences"] == "One language across agent and API."
    assert record["alternatives"] == ["Flask", "Django REST framework"]
