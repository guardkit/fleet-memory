"""Integration tests for search limit boundaries and empty store behavior.

Marker-gated (@pytest.mark.integration) tests validating:
- Limit parameter semantics (exactly N results for N in {1, 10, 15})
- Default limit behavior (at most 10 results when limit not specified)
- Empty store search (zero results, no error)

Requirements:
- Docker running for ephemeral_pg fixture
- Default test run (pytest) skips these; run with: pytest -m integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
async def test_search_limit_returns_exactly_n_results(store_context) -> None:
    """Limit boundaries: with 15 relevant memories, asearch returns exactly N for N in {1, 10, 15}.

    AC-001: Store 15 memories, then verify asearch(limit=N) returns exactly N results,
    best-ranked first (though ranking order is tested with real embeddings elsewhere).
    """
    store, namespace = store_context

    # Store 15 memories with searchable content
    for i in range(15):
        key = f"memory_{i:02d}"
        content = {
            "content": f"Test memory number {i} about database connection pooling and infrastructure",
            "index": i,
        }
        await store.aput(namespace, key, content)

    # Test limit=1: should return exactly 1 result
    results_1 = await store.asearch(namespace, query="database", limit=1)
    assert len(results_1) == 1, f"Expected 1 result with limit=1, got {len(results_1)}"

    # Test limit=10: should return exactly 10 results
    results_10 = await store.asearch(namespace, query="database", limit=10)
    assert len(results_10) == 10, f"Expected 10 results with limit=10, got {len(results_10)}"

    # Test limit=15: should return exactly 15 results (all of them)
    results_15 = await store.asearch(namespace, query="database", limit=15)
    assert len(results_15) == 15, f"Expected 15 results with limit=15, got {len(results_15)}"

    # Verify no duplicates across results
    keys_10 = {item.key for item in results_10}
    assert len(keys_10) == 10, "Results should contain unique keys only"


@pytest.mark.integration
async def test_search_default_limit_returns_at_most_10(store_context) -> None:
    """Default limit: asearch() without limit parameter returns at most 10 results.

    AC-002 (ASSUM-002): Store more than 10 memories (e.g., 15), then verify
    asearch() with no limit argument returns at most 10 results. Record the
    actual AsyncPostgresStore default; if it differs from 10, this test documents
    the observed contract for TASK-MEM-013.
    """
    store, namespace = store_context

    # Store 15 memories to exceed expected default limit
    for i in range(15):
        key = f"memory_{i:02d}"
        content = {
            "content": f"Memory {i} about Postgres connection pooling best practices",
            "index": i,
        }
        await store.aput(namespace, key, content)

    # Search without limit parameter (tests default behavior)
    results = await store.asearch(namespace, query="Postgres")

    # Verify at most 10 results (ASSUM-002 contract)
    assert len(results) <= 10, (
        f"Expected at most 10 results with default limit, got {len(results)}. "
        "If this differs from 10, update ASSUM-002 documentation with observed default."
    )

    # Document the actual observed default for reference
    # (Allows TASK-MEM-013 to reference the real contract)
    actual_default = len(results)
    assert actual_default > 0, "Search should return at least some results from 15 stored memories"

    # The actual default is expected to be 10, but we assert <= 10 to handle
    # if LangGraph's AsyncPostgresStore has a different default
    print(f"Observed default limit: {actual_default} (expected 10 per ASSUM-002)")


@pytest.mark.integration
async def test_search_empty_store_returns_zero_results(store_context) -> None:
    """Empty store: asearch on fresh namespace succeeds with zero results and no error.

    AC-003: Verify that searching an empty store (fresh namespace) returns an empty
    result list without raising any exceptions.
    """
    store, namespace = store_context

    # Search the fresh, empty namespace (no aput calls yet)
    results = await store.asearch(namespace, query="anything at all")

    # Verify zero results
    assert isinstance(results, list), "Search should return a list"
    assert len(results) == 0, f"Expected 0 results from empty store, got {len(results)}"

    # Verify no errors were raised (implicit - test passes if we get here)


@pytest.mark.integration
async def test_search_without_query_on_empty_store(store_context) -> None:
    """Empty store: asearch without query parameter also returns zero results.

    Supplements AC-003: verify behavior when listing all items from an empty namespace.
    """
    store, namespace = store_context

    # Search without query on empty namespace
    results = await store.asearch(namespace)

    # Verify zero results
    assert isinstance(results, list), "Search should return a list"
    assert len(results) == 0, f"Expected 0 results from empty store, got {len(results)}"
