"""Search finds live records ranked below records it filters out (3 November 2026).

Ordinary search used to take the store's top ten and filter afterwards, so ten
superseded or untagged records ranked first hid every live match below them.
Found seeding Bitwarden's decisions with replaced ones kept: the deciding record
could fall out of an agent's search. These tests use a real ephemeral PostgreSQL +
pgvector store and an embedder that places records by one marker word, so the
filtered-out records always rank above the one the search must return.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from fleet_memory.payloads.models import ADRPayload
from fleet_memory.retrieval.core import search
from fleet_memory.retrieval.search_request import SearchRequest
from fleet_memory.store import async_store_context
from fleet_memory.writer.core import DeterministicWriter

QUERY = "zebrafinch"


def _marker_embed(dims: int):
    """Texts containing the marker sit on the query's axis; the rest lean away."""

    def vector(text: str) -> list[float]:
        v = [0.0] * dims
        if text == QUERY or ('"old way ' + QUERY) in text:
            v[0] = 1.0
        elif QUERY in text:
            v[0], v[1] = 0.6, 0.8
        else:
            v[2] = 1.0
        return v

    async def embed(texts: list[str]) -> list[list[float]]:
        return [vector(text) for text in texts]

    return embed


@pytest.fixture
async def marker_store(test_settings):
    async with async_store_context(
        test_settings, embed_fn=_marker_embed(test_settings.embed_dims)
    ) as store:
        yield store


def _adr(project: str, identifier: str, decision: str, **extra) -> ADRPayload:
    return ADRPayload(
        project=project,
        identifier=identifier,
        decision=decision,
        status="accepted",
        source_ref="test_search_pages_past_filtered_records",
        **extra,
    )


def _request(project: str, **extra) -> SearchRequest:
    return SearchRequest(
        project=project, query=QUERY, token_budget=2000, payload_types=["adr"], **extra
    )


@pytest.mark.integration
async def test_twelve_superseded_records_do_not_hide_the_live_one(
    marker_store, test_settings
) -> None:
    project = f"paging_superseded_{uuid4().hex[:8]}"
    writer = DeterministicWriter(marker_store, test_settings)
    old = [_adr(project, f"OLD_{n:02d}", f"old way {QUERY} {n}") for n in range(12)]
    for record in old:
        await writer.write(record)
    await writer.write(
        _adr(project, "NEW", f"new way {QUERY}", supersedes=[r.natural_key for r in old])
    )

    results = await search(_request(project), marker_store)
    assert [r.value["identifier"] for r in results] == ["NEW"]

    # Positive control: the superseded records are there and rank first when asked for.
    shown = await search(_request(project, include_superseded=True), marker_store)
    assert len(shown) == 10
    assert "NEW" not in {r.value["identifier"] for r in shown}
    assert all(r.value.get("superseded_by") for r in shown)


@pytest.mark.integration
async def test_a_tag_filter_finds_records_ranked_below_untagged_ones(
    marker_store, test_settings
) -> None:
    project = f"paging_tags_{uuid4().hex[:8]}"
    writer = DeterministicWriter(marker_store, test_settings)
    for n in range(12):
        await writer.write(_adr(project, f"UNTAGGED_{n:02d}", f"old way {QUERY} {n}"))
    await writer.write(_adr(project, "TAGGED", f"new way {QUERY}", domain_tags=["auth"]))

    results = await search(_request(project, domain_tags=["auth"]), marker_store)
    assert [r.value["identifier"] for r in results] == ["TAGGED"]

    # Positive control: without the filter the untagged records fill the top ten.
    untagged = await search(_request(project), marker_store)
    assert len(untagged) == 10
    assert all(r.value["identifier"].startswith("UNTAGGED") for r in untagged)
