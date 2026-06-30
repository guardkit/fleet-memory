"""Unit tests for filtered vector search core.

Tests cover all acceptance criteria for TASK-RA-002:
- Project-scoped search with cosine similarity ranking
- Payload type filtering (0/1/many)
- Domain tag filtering
- Supersession handling (exclude by default, include if requested)
- Deterministic ordering for equal relevance
- Empty result handling
- Query text that resembles filter syntax
- Error handling for embed service and store unavailability
- Mid-search supersession consistency
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import json

import pytest
from langgraph.store.base import SearchItem

from fleet_memory.errors import EmbedServiceError
from fleet_memory.retrieval import SearchRequest
from fleet_memory.retrieval.core import (
    _item_domain_tags,
    _matches_domain_tags,
    search,
)


def _make_search_item(
    namespace: tuple[str, ...],
    key: str,
    value: dict,
    score: float,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> SearchItem:
    """Factory for SearchItem test data."""
    now = datetime.now(UTC)
    return SearchItem(
        namespace=namespace,
        key=key,
        value=value,
        score=score,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


# --- TASK-MEM08-012: domain_tags filter must read tags nested in the embedded
#     `content` JSON (the deterministic writer does not lift domain_tags to a
#     top-level stored field), else every typed payload is deselected by a tag filter.
def _ns():
    return ("fleet_memory", "guardkit", "build_outcome")


def test_item_domain_tags_prefers_top_level():
    item = _make_search_item(_ns(), "k", {"domain_tags": ["task"], "content": "{}"}, 0.9)
    assert _item_domain_tags(item) == ["task"]


def test_item_domain_tags_falls_back_to_content_json():
    # Typed-payload shape: tags live ONLY inside the embedded content JSON.
    content = json.dumps({"natural_key": "build_outcome:guardkit:T1", "domain_tags": ["task"]})
    item = _make_search_item(_ns(), "k", {"content": content}, 0.9)
    assert _item_domain_tags(item) == ["task"]


def test_item_domain_tags_chunk_prose_is_empty():
    # Chunk records carry prose (not JSON) in content and have no tags.
    item = _make_search_item(("fleet_memory", "guardkit", "chunk"), "k", {"content": "# A doc"}, 0.9)
    assert _item_domain_tags(item) == []


def test_matches_domain_tags_via_content_fallback():
    content = json.dumps({"domain_tags": ["task"]})
    item = _make_search_item(_ns(), "k", {"content": content}, 0.9)
    assert _matches_domain_tags(item, ["task"]) is True
    assert _matches_domain_tags(item, ["other"]) is False
    # No filter still matches everything.
    assert _matches_domain_tags(item, []) is True


@pytest.fixture
def make_search_request():
    """Factory fixture for SearchRequest test data."""

    def _make(**overrides):
        defaults = {
            "project": "test_project",
            "query": "test query",
            "token_budget": 2000,
        }
        defaults.update(overrides)
        return SearchRequest(**defaults)

    return _make


@pytest.mark.asyncio
async def test_search_returns_only_requested_project_memories_ranked_descending(
    make_search_request,
):
    """AC: Query returns only requested project's memories, ranked by cosine desc."""
    request = make_search_request(project="proj_a")

    # Mock store with memories from different projects
    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "proj_a", "document"),
            key="key1",
            value={"content": "memory 1", "natural_key": "document:proj_a:1"},
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "proj_a", "document"),
            key="key2",
            value={"content": "memory 2", "natural_key": "document:proj_a:2"},
            score=0.7,
        ),
        _make_search_item(
            namespace=("fleet_memory", "proj_a", "adr"),
            key="key3",
            value={"content": "memory 3", "natural_key": "adr:proj_a:3"},
            score=0.85,
        ),
    ]

    results = await search(request, mock_store)

    # Verify descending order by score
    assert len(results) == 3
    assert results[0].score == 0.9
    assert results[1].score == 0.85
    assert results[2].score == 0.7

    # Verify namespace prefix used for search
    mock_store.asearch.assert_called_once()
    call_args = mock_store.asearch.call_args
    assert call_args[0][0] == ("fleet_memory", "proj_a")


@pytest.mark.asyncio
async def test_search_with_zero_payload_types_returns_all_types(make_search_request):
    """AC: Restricting to payload types - zero means all registered types."""
    request = make_search_request(payload_types=[])

    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={"content": "doc", "natural_key": "document:test_project:1"},
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "adr"),
            key="key2",
            value={"content": "adr", "natural_key": "adr:test_project:2"},
            score=0.8,
        ),
    ]

    results = await search(request, mock_store)

    # All types returned
    assert len(results) == 2
    assert any("document" in r.value.get("natural_key", "") for r in results)
    assert any("adr" in r.value.get("natural_key", "") for r in results)


@pytest.mark.asyncio
async def test_search_with_one_payload_type_returns_only_that_type(make_search_request):
    """AC: Restricting to payload types - one type returns only that type."""
    request = make_search_request(payload_types=["document"])

    mock_store = AsyncMock()
    # Store returns all types but we filter
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={"content": "doc", "natural_key": "document:test_project:1"},
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "adr"),
            key="key2",
            value={"content": "adr", "natural_key": "adr:test_project:2"},
            score=0.8,
        ),
    ]

    results = await search(request, mock_store)

    # Only document type returned
    assert len(results) == 1
    assert "document:test_project:1" in results[0].value["natural_key"]


@pytest.mark.asyncio
async def test_search_with_many_payload_types_returns_those_types(make_search_request):
    """AC: Restricting to payload types - many types returns all specified."""
    request = make_search_request(payload_types=["document", "adr"])

    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={"content": "doc", "natural_key": "document:test_project:1"},
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "adr"),
            key="key2",
            value={"content": "adr", "natural_key": "adr:test_project:2"},
            score=0.8,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "pattern"),
            key="key3",
            value={"content": "pattern", "natural_key": "pattern:test_project:3"},
            score=0.7,
        ),
    ]

    results = await search(request, mock_store)

    # Only document and adr returned
    assert len(results) == 2
    natural_keys = [r.value["natural_key"] for r in results]
    assert "document:test_project:1" in natural_keys
    assert "adr:test_project:2" in natural_keys
    assert "pattern:test_project:3" not in natural_keys


@pytest.mark.asyncio
async def test_search_with_domain_tag_returns_only_tagged_memories(make_search_request):
    """AC: Restricting to domain tag returns only memories carrying that tag."""
    request = make_search_request(domain_tags=["authentication"])

    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={
                "content": "auth doc",
                "natural_key": "document:test_project:1",
                "domain_tags": ["authentication"],
            },
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key2",
            value={
                "content": "other doc",
                "natural_key": "document:test_project:2",
                "domain_tags": ["networking"],
            },
            score=0.8,
        ),
    ]

    results = await search(request, mock_store)

    # Only authentication tagged memory returned
    assert len(results) == 1
    assert "authentication" in results[0].value.get("domain_tags", [])


@pytest.mark.asyncio
async def test_search_excludes_superseded_records_by_default(make_search_request):
    """AC: Superseded records are excluded by default; only current successors return."""
    request = make_search_request(include_superseded=False)

    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={
                "content": "current doc",
                "natural_key": "document:test_project:1",
            },
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key2",
            value={
                "content": "superseded doc",
                "natural_key": "document:test_project:2",
                "superseded_by": "document:test_project:3",
            },
            score=0.8,
        ),
    ]

    results = await search(request, mock_store)

    # Only current (non-superseded) returned
    assert len(results) == 1
    assert "superseded_by" not in results[0].value


@pytest.mark.asyncio
async def test_search_includes_superseded_when_requested(make_search_request):
    """AC: include_superseded=True returns both superseded and current, marked."""
    request = make_search_request(include_superseded=True)

    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={
                "content": "current doc",
                "natural_key": "document:test_project:1",
            },
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key2",
            value={
                "content": "superseded doc",
                "natural_key": "document:test_project:2",
                "superseded_by": "document:test_project:3",
            },
            score=0.8,
        ),
    ]

    results = await search(request, mock_store)

    # Both returned
    assert len(results) == 2
    superseded_results = [r for r in results if "superseded_by" in r.value]
    current_results = [r for r in results if "superseded_by" not in r.value]
    assert len(superseded_results) == 1
    assert len(current_results) == 1


@pytest.mark.asyncio
async def test_search_orders_equal_relevance_deterministically(make_search_request):
    """AC: Equal relevance ordered deterministically - tie-break on natural_key."""
    request = make_search_request()

    mock_store = AsyncMock()
    # Same score for multiple items
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={
                "content": "doc c",
                "natural_key": "document:test_project:c",
            },
            score=0.8,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key2",
            value={
                "content": "doc a",
                "natural_key": "document:test_project:a",
            },
            score=0.8,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key3",
            value={
                "content": "doc b",
                "natural_key": "document:test_project:b",
            },
            score=0.8,
        ),
    ]

    results = await search(request, mock_store)

    # All same score, should be sorted by natural_key
    assert len(results) == 3
    assert all(r.score == 0.8 for r in results)
    # Deterministic ordering by natural_key
    natural_keys = [r.value["natural_key"] for r in results]
    assert natural_keys == sorted(natural_keys)


@pytest.mark.asyncio
async def test_search_empty_project_returns_empty_result(make_search_request):
    """AC: Search against project with no memories returns empty result, no error."""
    request = make_search_request(project="empty_project")

    mock_store = AsyncMock()
    mock_store.asearch.return_value = []

    results = await search(request, mock_store)

    assert results == []


@pytest.mark.asyncio
async def test_search_treats_filter_syntax_in_query_as_text(make_search_request):
    """AC: Query text resembling filter instruction is matched as query text only."""
    # This AC validates that we don't parse the query for special syntax
    request = make_search_request(
        query="payload_type:adr OR include_superseded=true"
    )

    mock_store = AsyncMock()
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={
                "content": "doc",
                "natural_key": "document:test_project:1",
                "superseded_by": "document:test_project:2",
            },
            score=0.9,
        ),
    ]

    results = await search(request, mock_store)

    # Superseded still excluded even though query mentions include_superseded
    assert len(results) == 0

    # Verify query passed as-is to asearch
    mock_store.asearch.assert_called_once()
    call_args = mock_store.asearch.call_args
    assert call_args[1]["query"] == "payload_type:adr OR include_superseded=true"


@pytest.mark.asyncio
async def test_search_raises_clear_error_when_embed_service_unavailable(
    make_search_request,
):
    """AC: When embedding service unavailable, fail with clear message, no credentials."""
    request = make_search_request()

    mock_store = AsyncMock()
    # Simulate embed service error during search
    mock_store.asearch.side_effect = EmbedServiceError(
        "Service unavailable", url="http://embed-service:9000"
    )

    with pytest.raises(EmbedServiceError) as exc_info:
        await search(request, mock_store)

    # Error message should be clear and not contain credentials
    error_msg = str(exc_info.value)
    assert "Embedding service error" in error_msg
    assert "unavailable" in error_msg
    # Should NOT contain database credentials (DSN, password, etc)
    assert "password" not in error_msg.lower()
    assert "postgresql://" not in error_msg


@pytest.mark.asyncio
async def test_search_raises_clear_error_when_store_unreachable(make_search_request):
    """AC: When store unreachable, caller receives clear failure, no credentials."""
    request = make_search_request()

    mock_store = AsyncMock()
    # Simulate timeout connecting to store
    mock_store.asearch.side_effect = TimeoutError(
        "Timed out connecting to Postgres at localhost:5432/fleet_memory after 5.0s"
    )

    with pytest.raises(TimeoutError) as exc_info:
        await search(request, mock_store)

    # Error message should be clear and not contain credentials
    error_msg = str(exc_info.value)
    assert "Timed out" in error_msg
    assert "Postgres" in error_msg
    # Should NOT contain credentials
    assert "password" not in error_msg.lower()


@pytest.mark.asyncio
async def test_search_mid_search_supersession_resolves_to_one_state(
    make_search_request,
):
    """AC: Record superseded mid-search resolves to exactly one state."""
    # This is more of a consistency test - in practice the store snapshot
    # should be consistent, but we verify the filtering logic is correct
    request = make_search_request(include_superseded=False)

    mock_store = AsyncMock()
    # Simulate a record that appears in multiple states (should not happen
    # in practice due to store semantics, but test our filtering)
    mock_store.asearch.return_value = [
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",
            value={
                "content": "doc version 1",
                "natural_key": "document:test_project:1",
                "superseded_by": "document:test_project:2",
            },
            score=0.9,
        ),
        _make_search_item(
            namespace=("fleet_memory", "test_project", "document"),
            key="key1",  # Same key
            value={
                "content": "doc version 2",
                "natural_key": "document:test_project:1",
            },
            score=0.9,
        ),
    ]

    results = await search(request, mock_store)

    # Should get only one result (the non-superseded one)
    assert len(results) == 1
    assert "superseded_by" not in results[0].value


@pytest.mark.seam
@pytest.mark.integration_contract("SearchRequest")
def test_search_core_consumes_validated_request():
    """Seam test: verify SearchRequest contract from TASK-RA-001.

    Contract: request is validated upstream; search core executes, never re-validates.
    Producer: TASK-RA-001
    """
    req = SearchRequest(project="guardkit", query="retries", token_budget=2000)
    assert req.project == "guardkit"
    assert req.include_superseded is False
    # Consumer side: search core must read fields, not re-run validation
    # (e.g. it must not raise on a request that already passed model validation)
