"""Unit tests for job-specific composition by complexity band.

Tests all acceptance criteria from TASK-RA-004:
- AC-1: Complexity band controls type mix and per-type budget share
- AC-2: Complex jobs include more patterns/warnings than simple jobs
- AC-3: All blocks remain within token budgets
- AC-4: Band names defined as single source of truth
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langgraph.store.base import SearchItem

from fleet_memory.retrieval.assembly import assemble_context
from fleet_memory.retrieval.composition import (
    ComplexityBand,
    compose_by_complexity,
)


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


def test_complexity_band_enum_exists():
    """AC-4: Band names defined as single source of truth (enum/constant)."""
    assert ComplexityBand.SIMPLE == "simple"
    assert ComplexityBand.STANDARD == "standard"
    assert ComplexityBand.COMPLEX == "complex"


def test_simple_band_reduces_pattern_and_warning_share():
    """AC-2: Simple jobs get fewer patterns/warnings than standard jobs."""
    # Create mixed results with patterns, warnings, and documents
    items = [
        _create_search_item("pattern:proj:1", "Pattern A" * 20, score=0.95),
        _create_search_item("pattern:proj:2", "Pattern B" * 20, score=0.94),
        _create_search_item("warning:proj:1", "Warning A" * 20, score=0.93),
        _create_search_item("warning:proj:2", "Warning B" * 20, score=0.92),
        _create_search_item("document:proj:1", "Doc A" * 20, score=0.91),
        _create_search_item("document:proj:2", "Doc B" * 20, score=0.90),
    ]

    # Compose for simple band (should favor documents over patterns/warnings)
    simple_composed = compose_by_complexity(
        items, complexity_band=ComplexityBand.SIMPLE
    )

    # Compose for standard band (balanced mix)
    standard_composed = compose_by_complexity(
        items, complexity_band=ComplexityBand.STANDARD
    )

    # Count patterns and warnings in each composition
    simple_pw_count = sum(
        1
        for item in simple_composed
        if item.value["natural_key"].startswith(("pattern:", "warning:"))
    )
    standard_pw_count = sum(
        1
        for item in standard_composed
        if item.value["natural_key"].startswith(("pattern:", "warning:"))
    )

    # Simple should have fewer patterns/warnings than standard
    assert simple_pw_count < standard_pw_count


def test_complex_band_increases_pattern_and_warning_share():
    """AC-2: Complex jobs get more patterns/warnings than standard jobs."""
    # Create mixed results
    items = [
        _create_search_item("pattern:proj:1", "Pattern A" * 20, score=0.95),
        _create_search_item("pattern:proj:2", "Pattern B" * 20, score=0.94),
        _create_search_item("pattern:proj:3", "Pattern C" * 20, score=0.93),
        _create_search_item("warning:proj:1", "Warning A" * 20, score=0.92),
        _create_search_item("warning:proj:2", "Warning B" * 20, score=0.91),
        _create_search_item("warning:proj:3", "Warning C" * 20, score=0.90),
        _create_search_item("document:proj:1", "Doc A" * 20, score=0.89),
        _create_search_item("document:proj:2", "Doc B" * 20, score=0.88),
    ]

    # Compose for complex band (should favor patterns/warnings)
    complex_composed = compose_by_complexity(
        items, complexity_band=ComplexityBand.COMPLEX
    )

    # Compose for standard band (balanced mix)
    standard_composed = compose_by_complexity(
        items, complexity_band=ComplexityBand.STANDARD
    )

    # Count patterns and warnings
    complex_pw_count = sum(
        1
        for item in complex_composed
        if item.value["natural_key"].startswith(("pattern:", "warning:"))
    )
    standard_pw_count = sum(
        1
        for item in standard_composed
        if item.value["natural_key"].startswith(("pattern:", "warning:"))
    )

    # Complex should have more patterns/warnings than standard
    assert complex_pw_count > standard_pw_count


def test_composition_respects_token_budget():
    """AC-3: Composed blocks remain within token budgets."""
    # Create many items
    items = [
        _create_search_item("pattern:proj:1", "Pattern A" * 100, score=0.95),
        _create_search_item("warning:proj:1", "Warning A" * 100, score=0.94),
        _create_search_item("document:proj:1", "Doc A" * 100, score=0.93),
        _create_search_item("pattern:proj:2", "Pattern B" * 100, score=0.92),
        _create_search_item("warning:proj:2", "Warning B" * 100, score=0.91),
        _create_search_item("document:proj:2", "Doc B" * 100, score=0.90),
    ]

    token_budget = 500

    # Test all complexity bands
    for band in [ComplexityBand.SIMPLE, ComplexityBand.STANDARD, ComplexityBand.COMPLEX]:
        composed = compose_by_complexity(items, complexity_band=band)
        result = assemble_context(composed, token_budget=token_budget)

        # All bands must respect the budget
        assert result.tokens_used <= token_budget, (
            f"{band} band exceeded budget: {result.tokens_used} > {token_budget}"
        )


def test_composition_preserves_empty_results():
    """Composition with empty results returns empty list."""
    result = compose_by_complexity([], complexity_band=ComplexityBand.SIMPLE)
    assert result == []


def test_composition_with_only_documents():
    """Composition works when only documents are present (no patterns/warnings)."""
    items = [
        _create_search_item("document:proj:1", "Doc A" * 20, score=0.95),
        _create_search_item("document:proj:2", "Doc B" * 20, score=0.94),
    ]

    # All bands should return the same results when only documents exist
    simple = compose_by_complexity(items, complexity_band=ComplexityBand.SIMPLE)
    complex_result = compose_by_complexity(items, complexity_band=ComplexityBand.COMPLEX)

    # Both should contain the documents
    assert len(simple) == 2
    assert len(complex_result) == 2


def test_composition_with_only_patterns_and_warnings():
    """Composition works when only patterns/warnings are present."""
    items = [
        _create_search_item("pattern:proj:1", "Pattern A" * 20, score=0.95),
        _create_search_item("warning:proj:1", "Warning A" * 20, score=0.94),
    ]

    # All bands should include patterns/warnings
    simple = compose_by_complexity(items, complexity_band=ComplexityBand.SIMPLE)
    complex_result = compose_by_complexity(items, complexity_band=ComplexityBand.COMPLEX)

    assert len(simple) >= 1
    assert len(complex_result) >= 1


@pytest.mark.seam
@pytest.mark.integration_contract("AssembledContext")
def test_composition_respects_budget_from_assembly():
    """Composition tunes the mix but assembly still enforces the budget.

    Contract: composition adjusts type/budget share; the assembled block must
    still not exceed token_budget.
    Producer: TASK-RA-003
    """
    items = [
        _create_search_item("pattern:proj:1", "P" * 200, score=0.95),
        _create_search_item("warning:proj:1", "W" * 200, score=0.94),
        _create_search_item("document:proj:1", "D" * 200, score=0.93),
    ]

    token_budget = 300

    # Complex band should include more patterns/warnings
    complex_composed = compose_by_complexity(items, complexity_band=ComplexityBand.COMPLEX)
    assembly_result = assemble_context(complex_composed, token_budget=token_budget)

    # Assembly must enforce the budget (composition doesn't bypass it)
    assert assembly_result.tokens_used <= token_budget

    # Verify patterns or warnings contributed
    has_pattern_or_warning = any(
        typ in assembly_result.contributing_types for typ in ["pattern", "warning"]
    )
    assert has_pattern_or_warning
