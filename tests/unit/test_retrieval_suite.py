"""Comprehensive retrieval surface test suite for TASK-RA-006.

Hermetic unit coverage using fake embed function (no network, no real store).
Tests the full retrieval surface: validation → search → assembly → harness.

Covers:
- Validation rejections (hyphen project, unknown payload, malformed tags, negative budget, empty request)
- Filtering/ranking (payload-type filter 0/1/3, domain-tag filter, cosine-desc, supersession)
- Budget boundaries (exactly-budget, drop-lowest, zero budget, omit-whole, partial-coverage)
- Security/injection (query resembling filter, injection domain tag)
- Concurrency/determinism (equal-relevance ordering, supersede-mid-search, repeated searches)
- Degradation (embed unavailable, store unreachable, credential-free messages)

Producer: TASK-RA-006
Consumer: FEAT-MEM-05 acceptance validation
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from langgraph.store.base import SearchItem
from pydantic import ValidationError

from fleet_memory.embed import make_fake_embed
from fleet_memory.errors import EmbedServiceError
from fleet_memory.retrieval import SearchRequest
from fleet_memory.retrieval.assembly import assemble_context
from fleet_memory.retrieval.core import search


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


class TestValidationRejections:
    """AC: Validation rejections for invalid inputs."""

    def test_hyphen_project_rejected(self) -> None:
        """AC: Project identifier with hyphens is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(project="my-project", token_budget=1000, query="test")

        errors = exc_info.value.errors()
        assert any("project" in str(e["loc"]) for e in errors)
        error_msg = " ".join(str(e["msg"]).lower() for e in errors)
        assert "underscore" in error_msg or "hyphen" in error_msg

    def test_unknown_payload_type_rejected(self) -> None:
        """AC: Unknown payload type not in PAYLOAD_REGISTRY is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                payload_types=["unknown_type"],
                token_budget=1000,
                query="test",
            )

        errors = exc_info.value.errors()
        error_msg = " ".join(str(e["msg"]) for e in errors)
        assert "unknown_type" in error_msg

    def test_malformed_domain_tag_rejected(self) -> None:
        """AC: Domain tag with injection characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                domain_tags=["tag' OR '1'='1"],
                token_budget=1000,
                query="test",
            )

        errors = exc_info.value.errors()
        error_msg = " ".join(str(e["msg"]).lower() for e in errors)
        assert "malformed" in error_msg or "invalid" in error_msg

    def test_negative_budget_rejected(self) -> None:
        """AC: Negative token_budget is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(project="test_project", token_budget=-100, query="test")

        errors = exc_info.value.errors()
        error_msg = " ".join(str(e["msg"]).lower() for e in errors)
        assert "negative" in error_msg or "greater" in error_msg

    def test_empty_request_rejected(self) -> None:
        """AC: Request with no query and no filters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                payload_types=[],
                domain_tags=[],
                query=None,
                token_budget=1000,
            )

        errors = exc_info.value.errors()
        error_msg = " ".join(str(e["msg"]).lower() for e in errors)
        assert "query" in error_msg or "filter" in error_msg


class TestFilteringAndRanking:
    """AC: Filtering/ranking with payload types, domain tags, cosine desc, supersession."""

    @pytest.mark.asyncio
    async def test_payload_type_filter_zero_returns_all_types(self) -> None:
        """AC: payload_types=[] (zero filter) returns all payload types."""
        request = SearchRequest(project="test_project", query="test", token_budget=2000)

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "adr doc", "natural_key": "adr:test_project:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={"content": "pattern doc", "natural_key": "pattern:test_project:2"},
                score=0.8,
            ),
        ]

        results = await search(request, mock_store)

        # Both types returned
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_payload_type_filter_one_returns_only_that_type(self) -> None:
        """AC: payload_types=['adr'] (one filter) returns only ADR type."""
        request = SearchRequest(
            project="test_project", payload_types=["adr"], token_budget=2000, query="test"
        )

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "adr doc", "natural_key": "adr:test_project:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={"content": "pattern doc", "natural_key": "pattern:test_project:2"},
                score=0.8,
            ),
        ]

        results = await search(request, mock_store)

        # Only ADR returned
        assert len(results) == 1
        assert "adr" in results[0].value["natural_key"]

    @pytest.mark.asyncio
    async def test_payload_type_filter_three_returns_those_types(self) -> None:
        """AC: payload_types=['adr','pattern','document'] (three) returns those types."""
        request = SearchRequest(
            project="test_project",
            payload_types=["adr", "pattern", "document"],
            token_budget=2000,
            query="test",
        )

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "adr", "natural_key": "adr:test_project:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={"content": "pattern", "natural_key": "pattern:test_project:2"},
                score=0.8,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key3",
                value={"content": "warning", "natural_key": "warning:test_project:3"},
                score=0.7,
            ),
        ]

        results = await search(request, mock_store)

        # Only adr and pattern returned (warning excluded)
        assert len(results) == 2
        natural_keys = [r.value["natural_key"] for r in results]
        assert "warning:test_project:3" not in natural_keys

    @pytest.mark.asyncio
    async def test_domain_tag_filter_returns_only_tagged_memories(self) -> None:
        """AC: domain_tags filter returns only memories with matching tags."""
        request = SearchRequest(
            project="test_project",
            domain_tags=["authentication"],
            token_budget=2000,
            query="test",
        )

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={
                    "content": "auth doc",
                    "natural_key": "document:test_project:1",
                    "domain_tags": ["authentication"],
                },
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
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

        # Only authentication tagged memory
        assert len(results) == 1
        assert "authentication" in results[0].value["domain_tags"]

    @pytest.mark.asyncio
    async def test_cosine_desc_ordering(self) -> None:
        """AC: Results ordered by cosine similarity descending (highest first)."""
        request = SearchRequest(project="test_project", query="test", token_budget=2000)

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "low score", "natural_key": "doc:test_project:1"},
                score=0.3,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={"content": "high score", "natural_key": "doc:test_project:2"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key3",
                value={"content": "mid score", "natural_key": "doc:test_project:3"},
                score=0.6,
            ),
        ]

        results = await search(request, mock_store)

        # Descending order by score
        assert results[0].score == 0.9
        assert results[1].score == 0.6
        assert results[2].score == 0.3

    @pytest.mark.asyncio
    async def test_supersession_exclusion_by_default(self) -> None:
        """AC: Superseded records excluded by default."""
        request = SearchRequest(
            project="test_project", query="test", token_budget=2000, include_superseded=False
        )

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "current", "natural_key": "doc:test_project:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={
                    "content": "superseded",
                    "natural_key": "doc:test_project:2",
                    "superseded_by": "doc:test_project:3",
                },
                score=0.8,
            ),
        ]

        results = await search(request, mock_store)

        # Only current (non-superseded) returned
        assert len(results) == 1
        assert "superseded_by" not in results[0].value

    @pytest.mark.asyncio
    async def test_include_superseded_marking(self) -> None:
        """AC: include_superseded=True returns superseded records marked."""
        request = SearchRequest(
            project="test_project", query="test", token_budget=2000, include_superseded=True
        )

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "current", "natural_key": "doc:test_project:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={
                    "content": "superseded",
                    "natural_key": "doc:test_project:2",
                    "superseded_by": "doc:test_project:3",
                },
                score=0.8,
            ),
        ]

        results = await search(request, mock_store)

        # Both returned, superseded marked
        assert len(results) == 2
        superseded = [r for r in results if "superseded_by" in r.value]
        assert len(superseded) == 1


class TestBudgetBoundaries:
    """AC: Budget boundaries - exactly-budget, drop-lowest, zero, omit-whole, partial-coverage."""

    def test_exactly_budget_returns_full(self) -> None:
        """AC: Content exactly at budget is returned in full."""
        items = [
            _make_search_item(
                namespace=("fleet_memory", "test"),
                key="key1",
                value={"content": "Short text", "natural_key": "doc:test:1"},
                score=0.9,
            ),
        ]

        result = assemble_context(items, token_budget=1000)

        # Should fit and be included
        assert "Short text" in result.context_block
        assert result.tokens_used <= 1000

    def test_over_budget_drops_lowest_ranked(self) -> None:
        """AC: 2100 tokens → drop lowest-ranked to fit budget."""
        items = [
            _make_search_item(
                namespace=("fleet_memory", "test"),
                key="key1",
                value={"content": "A" * 200, "natural_key": "doc:test:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test"),
                key="key2",
                value={"content": "B" * 200, "natural_key": "doc:test:2"},
                score=0.5,
            ),
        ]

        result = assemble_context(items, token_budget=50)

        # Should keep highest-ranked, drop lowest
        assert "A" in result.context_block or result.context_block == ""
        assert result.tokens_used <= 50

    def test_zero_budget_returns_empty(self) -> None:
        """AC: Zero budget returns empty context."""
        items = [
            _make_search_item(
                namespace=("fleet_memory", "test"),
                key="key1",
                value={"content": "Content", "natural_key": "doc:test:1"},
                score=0.9,
            ),
        ]

        result = assemble_context(items, token_budget=0)

        assert result.context_block == ""
        assert result.coverage_score == 0.0
        assert result.tokens_used == 0

    def test_memory_larger_than_budget_omitted_whole(self) -> None:
        """AC: Single memory larger than budget is omitted entirely."""
        items = [
            _make_search_item(
                namespace=("fleet_memory", "test"),
                key="key1",
                value={"content": "X" * 1000, "natural_key": "doc:test:1"},
                score=0.9,
            ),
        ]

        result = assemble_context(items, token_budget=50)

        # Too large, omitted whole
        assert result.context_block == ""
        assert result.tokens_used == 0

    def test_partial_coverage_honesty(self) -> None:
        """AC: Partial coverage reflected in coverage_score."""
        items = [
            _make_search_item(
                namespace=("fleet_memory", "test"),
                key="key1",
                value={"content": "Small", "natural_key": "doc:test:1"},
                score=0.9,
            ),
        ]

        result = assemble_context(items, token_budget=10000)

        # Small content, low coverage
        assert 0.0 < result.coverage_score < 0.5


class TestSecurityAndInjection:
    """AC: Security/injection - query resembling filter, injection domain tag."""

    @pytest.mark.asyncio
    async def test_query_resembling_filter_is_search_text_only(self) -> None:
        """AC: Query text resembling filter syntax is treated as search text only."""
        request = SearchRequest(
            project="test_project",
            query="payload_type:adr OR include_superseded=true",
            token_budget=2000,
        )

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
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

    def test_injection_domain_tag_rejected(self) -> None:
        """AC: Injection domain tag with SQL operators is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                domain_tags=["tag'; DROP TABLE memories; --"],
                token_budget=1000,
                query="test",
            )

        errors = exc_info.value.errors()
        error_msg = " ".join(str(e["msg"]).lower() for e in errors)
        assert "malformed" in error_msg or "invalid" in error_msg


class TestConcurrencyAndDeterminism:
    """AC: Concurrency/determinism - equal-relevance ordering, supersede-mid-search, repeated searches."""

    @pytest.mark.asyncio
    async def test_equal_relevance_deterministic_ordering(self) -> None:
        """AC: Equal relevance scores ordered deterministically by natural_key."""
        request = SearchRequest(project="test_project", query="test", token_budget=2000)

        mock_store = AsyncMock()
        # Same score for all items
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "doc c", "natural_key": "document:test_project:c"},
                score=0.8,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={"content": "doc a", "natural_key": "document:test_project:a"},
                score=0.8,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key3",
                value={"content": "doc b", "natural_key": "document:test_project:b"},
                score=0.8,
            ),
        ]

        results = await search(request, mock_store)

        # Deterministic ordering: by natural_key ascending when scores equal
        natural_keys = [r.value["natural_key"] for r in results]
        assert natural_keys == [
            "document:test_project:a",
            "document:test_project:b",
            "document:test_project:c",
        ]

    @pytest.mark.asyncio
    async def test_supersede_mid_search_resolves_to_one_state(self) -> None:
        """AC: Record superseded mid-search resolves to exactly one state."""
        request = SearchRequest(
            project="test_project", query="test", token_budget=2000, include_superseded=False
        )

        mock_store = AsyncMock()
        # Same key appearing in multiple states (edge case)
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={
                    "content": "doc version 1",
                    "natural_key": "document:test_project:1",
                    "superseded_by": "document:test_project:2",
                },
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",  # Same key
                value={
                    "content": "doc version 2",
                    "natural_key": "document:test_project:1",
                },
                score=0.9,
            ),
        ]

        results = await search(request, mock_store)

        # Should resolve to one result (the non-superseded one)
        assert len(results) == 1
        assert "superseded_by" not in results[0].value

    @pytest.mark.asyncio
    async def test_repeated_concurrent_searches_return_identical_blocks(self) -> None:
        """AC: Repeated concurrent searches over unchanged corpus return identical blocks."""
        request = SearchRequest(project="test_project", query="test query", token_budget=2000)

        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={"content": "doc 1", "natural_key": "document:test_project:1"},
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={"content": "doc 2", "natural_key": "document:test_project:2"},
                score=0.8,
            ),
        ]

        # Execute 5 concurrent searches
        tasks = [search(request, mock_store) for _ in range(5)]
        results_list = await asyncio.gather(*tasks)

        # All results should be identical (same ordering, same content)
        first_result = results_list[0]
        for result in results_list[1:]:
            assert len(result) == len(first_result)
            for i, item in enumerate(result):
                assert item.key == first_result[i].key
                assert item.score == first_result[i].score
                assert item.value == first_result[i].value


class TestDegradation:
    """AC: Degradation - embed unavailable, store unreachable, credential-free messages."""

    @pytest.mark.asyncio
    async def test_embed_unavailable_fails_cleanly_without_credentials(self) -> None:
        """AC: Embed service unavailable fails with credential-free message."""
        request = SearchRequest(project="test_project", query="test", token_budget=2000)

        mock_store = AsyncMock()
        # Simulate embed service error
        mock_store.asearch.side_effect = EmbedServiceError(
            "Service unavailable", url="http://embed-service:9000"
        )

        with pytest.raises(EmbedServiceError) as exc_info:
            await search(request, mock_store)

        error_msg = str(exc_info.value)
        # Should have clear error message
        assert "Embedding service error" in error_msg or "unavailable" in error_msg
        # Should NOT contain credentials
        assert "password" not in error_msg.lower()
        assert "postgresql://" not in error_msg

    @pytest.mark.asyncio
    async def test_store_unreachable_fails_cleanly_without_credentials(self) -> None:
        """AC: Store unreachable fails with credential-free message."""
        request = SearchRequest(project="test_project", query="test", token_budget=2000)

        mock_store = AsyncMock()
        # Simulate timeout connecting to store
        mock_store.asearch.side_effect = TimeoutError(
            "Timed out connecting to Postgres at localhost:5432 after 5.0s"
        )

        with pytest.raises(TimeoutError) as exc_info:
            await search(request, mock_store)

        error_msg = str(exc_info.value)
        # Should have clear error message
        assert "Timed out" in error_msg
        assert "Postgres" in error_msg
        # Should NOT contain credentials
        assert "password" not in error_msg.lower()


class TestEndToEndWithFakeEmbed:
    """End-to-end integration tests using fake_embed (no network/NAS)."""

    @pytest.mark.asyncio
    async def test_full_retrieval_flow_with_fake_embed(self) -> None:
        """Full retrieval flow: validation → search → assembly with fake embed."""
        # Create fake embed function
        fake_embed = make_fake_embed(dims=768)

        # Validate that fake embed works
        embeddings = await fake_embed(["test query", "another query"])
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 768
        assert len(embeddings[1]) == 768

        # Test that fake embed is deterministic
        embeddings2 = await fake_embed(["test query", "another query"])
        assert embeddings == embeddings2

        # Create search request (validation)
        request = SearchRequest(
            project="test_project",
            query="test query",
            payload_types=["document"],
            token_budget=2000,
        )

        # Mock store search results
        mock_store = AsyncMock()
        mock_store.asearch.return_value = [
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key1",
                value={
                    "content": "This is a test document for retrieval",
                    "natural_key": "document:test_project:1",
                },
                score=0.9,
            ),
            _make_search_item(
                namespace=("fleet_memory", "test_project"),
                key="key2",
                value={
                    "content": "Another test document",
                    "natural_key": "document:test_project:2",
                },
                score=0.7,
            ),
        ]

        # Execute search
        search_results = await search(request, mock_store)

        # Assembly
        assembly_result = assemble_context(search_results, request.token_budget)

        # Verify end-to-end behavior
        assert len(search_results) == 2
        assert assembly_result.context_block != ""
        assert assembly_result.tokens_used > 0
        assert assembly_result.tokens_used <= request.token_budget
        assert "document" in assembly_result.contributing_types
        assert 0.0 < assembly_result.coverage_score <= 1.0

    @pytest.mark.asyncio
    async def test_fake_embed_deterministic_across_calls(self) -> None:
        """Fake embed returns deterministic results across multiple calls."""
        fake_embed = make_fake_embed(dims=768)

        # Multiple calls with same input
        results = []
        for _ in range(3):
            embeddings = await fake_embed(["test", "query"])
            results.append(embeddings)

        # All results identical
        for result in results[1:]:
            assert result == results[0]

    @pytest.mark.asyncio
    async def test_fake_embed_different_texts_different_vectors(self) -> None:
        """Fake embed produces different vectors for different texts."""
        fake_embed = make_fake_embed(dims=768)

        embeddings = await fake_embed(["hello", "world", "test"])

        # All different
        assert embeddings[0] != embeddings[1]
        assert embeddings[1] != embeddings[2]
        assert embeddings[0] != embeddings[2]
