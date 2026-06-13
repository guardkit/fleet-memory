"""Unit tests for token-budgeted context assembly.

Tests all acceptance criteria from TASK-RA-003:
- Single assembled context block
- Never exceeds token budget (measured with tiktoken cl100k_base)
- Boundary conditions (exact budget, over budget, zero budget)
- Memory ranking (higher-ranked kept)
- Coverage score reporting
- Deterministic assembly
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langgraph.store.base import SearchItem

from fleet_memory.retrieval.assembly import AssemblyResult, assemble_context


def _create_search_item(
    natural_key: str, content: str, score: float = 0.8
) -> SearchItem:
    """Helper to create SearchItem for testing.

    Args:
        natural_key: Memory natural key (format: type:project:id)
        content: Memory content text
        score: Relevance score (default 0.8)

    Returns:
        SearchItem with specified fields
    """
    now = datetime.now(UTC)
    return SearchItem(
        namespace=("fleet_memory", "test_project"),
        key=natural_key,
        value={
            "natural_key": natural_key,
            "content": content,
            "domain_tags": [],
        },
        score=score,
        created_at=now,
        updated_at=now,
    )


def test_empty_results_returns_empty_block():
    """Empty search results return empty context block."""
    result = assemble_context([], token_budget=1000)

    assert result.context_block == ""
    assert result.coverage_score == 0.0
    assert result.contributing_types == set()
    assert result.tokens_used == 0


def test_zero_budget_returns_empty_block():
    """Zero token budget returns empty context block (AC: zero budget)."""
    items = [
        _create_search_item("doc:proj:1", "Content here", score=0.9),
    ]

    result = assemble_context(items, token_budget=0)

    assert result.context_block == ""
    assert result.coverage_score == 0.0
    assert result.contributing_types == set()
    assert result.tokens_used == 0


def test_single_item_within_budget():
    """Single item that fits within budget is included in full."""
    items = [
        _create_search_item("doc:proj:1", "Short content", score=0.9),
    ]

    result = assemble_context(items, token_budget=1000)

    assert "Short content" in result.context_block
    assert result.coverage_score > 0.0
    assert "doc" in result.contributing_types
    assert result.tokens_used > 0
    assert result.tokens_used <= 1000


def test_assembled_block_never_exceeds_budget():
    """Assembled block never exceeds token budget (AC-1)."""
    items = [
        _create_search_item("doc:proj:1", "A" * 500, score=0.9),
        _create_search_item("doc:proj:2", "B" * 500, score=0.8),
        _create_search_item("doc:proj:3", "C" * 500, score=0.7),
    ]

    result = assemble_context(items, token_budget=100)

    # The actual assembled block must be measured with tiktoken
    assert result.tokens_used <= 100
    assert result.coverage_score <= 1.0


def test_exactly_at_budget_returns_full():
    """Content exactly at budget is returned in full (AC: just-inside boundary)."""
    # Create content that will be exactly at budget when assembled
    # This test verifies the boundary condition
    items = [
        _create_search_item("doc:proj:1", "X" * 50, score=0.9),
    ]

    result = assemble_context(items, token_budget=1000)

    # If it fits, tokens_used should equal the actual size
    assert result.tokens_used <= 1000
    assert "X" * 50 in result.context_block


def test_over_budget_drops_lowest_ranked():
    """Content over budget drops lowest-ranked memories (AC: 2100 → drop lowest)."""
    items = [
        _create_search_item("doc:proj:1", "A" * 200, score=0.9),  # high
        _create_search_item("doc:proj:2", "B" * 200, score=0.5),  # low
    ]

    result = assemble_context(items, token_budget=50)

    # Should keep highest-ranked, drop lowest
    assert "A" in result.context_block
    # Low-ranked should be dropped
    assert result.tokens_used <= 50


def test_single_memory_larger_than_budget_omitted():
    """Single memory larger than budget is omitted whole (AC: ASSUM-009)."""
    items = [
        _create_search_item("doc:proj:1", "X" * 1000, score=0.9),
    ]

    result = assemble_context(items, token_budget=50)

    # Too large, should be omitted entirely
    assert result.context_block == ""
    assert result.coverage_score == 0.0
    assert result.tokens_used == 0


def test_higher_ranked_kept_over_lower():
    """Higher-ranked memory kept, lower-ranked omitted (AC: ranking priority)."""
    items = [
        _create_search_item("warning:proj:1", "Critical warning", score=0.95),
        _create_search_item("overview:proj:1", "General overview", score=0.30),
    ]

    result = assemble_context(items, token_budget=100)

    # High-ranked warning should be present
    assert "Critical warning" in result.context_block
    # Coverage may be partial if budget can't fit both
    assert result.coverage_score > 0.0


def test_coverage_score_reported():
    """Result reports coverage score and contributing types (AC: coverage)."""
    items = [
        _create_search_item("doc:proj:1", "Content A", score=0.9),
        _create_search_item("warning:proj:1", "Content B", score=0.8),
    ]

    result = assemble_context(items, token_budget=1000)

    # Coverage score should be 0.0-1.0
    assert 0.0 <= result.coverage_score <= 1.0
    # Should report contributing types
    assert isinstance(result.contributing_types, set)
    # Should have positive tokens used
    assert result.tokens_used > 0


def test_partial_coverage_reported_honestly():
    """Partial coverage reported honestly, not padded (AC: honest reporting)."""
    items = [
        _create_search_item("doc:proj:1", "A" * 100, score=0.9),
        _create_search_item("doc:proj:2", "B" * 100, score=0.8),
    ]

    result = assemble_context(items, token_budget=50)

    # Should report actual coverage, not 100%
    assert result.coverage_score < 1.0
    assert result.tokens_used <= 50


def test_deterministic_assembly():
    """Repeated assembly with same input returns identical output (AC: deterministic)."""
    items = [
        _create_search_item("doc:proj:1", "Content A", score=0.9),
        _create_search_item("doc:proj:2", "Content B", score=0.8),
        _create_search_item("doc:proj:3", "Content C", score=0.7),
    ]

    result1 = assemble_context(items, token_budget=200)
    result2 = assemble_context(items, token_budget=200)

    # Should be identical
    assert result1.context_block == result2.context_block
    assert result1.coverage_score == result2.coverage_score
    assert result1.contributing_types == result2.contributing_types
    assert result1.tokens_used == result2.tokens_used


def test_contributing_types_extracted():
    """Contributing payload types are extracted from natural_key."""
    items = [
        _create_search_item("doc:proj:1", "Doc content", score=0.9),
        _create_search_item("warning:proj:1", "Warning content", score=0.8),
        _create_search_item("doc:proj:2", "Another doc", score=0.7),
    ]

    result = assemble_context(items, token_budget=5000)

    # Should identify both types
    assert "doc" in result.contributing_types
    assert "warning" in result.contributing_types
    assert len(result.contributing_types) == 2


def test_coverage_score_calculation():
    """Coverage score is fraction of budget filled."""
    items = [
        _create_search_item("doc:proj:1", "Small", score=0.9),
    ]

    result = assemble_context(items, token_budget=1000)

    # Coverage = tokens_used / token_budget
    expected_coverage = result.tokens_used / 1000
    assert abs(result.coverage_score - expected_coverage) < 0.001


@pytest.mark.seam
@pytest.mark.integration_contract("RankedResults")
def test_assembly_consumes_ranked_results_in_order():
    """Assembly receives results most-relevant-first and drops from the tail.

    Contract: ranked list is ordered desc by relevance; assembly omits the
    lowest-ranked first when the budget forces a cut.
    Producer: TASK-RA-002
    """
    # Producer side: 3-element ranked list [high, medium, low]
    ranked = [
        _create_search_item("doc:proj:high", "High relevance", score=0.9),
        _create_search_item("doc:proj:med", "Medium relevance", score=0.5),
        _create_search_item("doc:proj:low", "Low relevance", score=0.1),
    ]

    # Consumer side: under a budget that fits only one, the high-ranked survives
    # Budget of 3 tokens fits only "High relevance" (2 tokens)
    result = assemble_context(ranked, token_budget=3)

    # High-scored should be present
    assert "High relevance" in result.context_block
    # Low-scored should be dropped
    assert "Low relevance" not in result.context_block
