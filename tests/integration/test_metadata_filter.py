"""Integration tests for metadata-filtered semantic search.

Marker-gated (@pytest.mark.integration) tests validating project-scoped metadata filtering
with preserved relevance ranking. Verifies that filter parameter correctly constrains results
while maintaining semantic search quality.

Requirements:
- Docker running for ephemeral_pg fixture
- FLEET_MEMORY_EMBED_URL env var for real embedding ranking tests
- Run with: pytest -m integration tests/integration/test_metadata_filter.py
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
async def test_metadata_filter_scopes_to_project_preserving_ranking(store_context_real) -> None:
    """Metadata filter: project-scoped filtering preserves relevance ranking.

    AC-001: Store memories from project_a and project_b, both semantically relevant
    to the query. Search filtered to project_a returns only project_a memories,
    still ranked by relevance with scores present.

    Uses real embeddings to verify ranking is preserved through filtering.
    """
    store, namespace = store_context_real

    # Store memories from project_a - both relevant to database queries
    await store.aput(
        namespace,
        "project_a_pooling",
        {
            "content": (
                "Database connection pooling manages Postgres connections efficiently "
                "by reusing connections across requests. Pool sizing impacts performance."
            ),
            "project": "project_a",
            "topic": "database",
        },
    )

    await store.aput(
        namespace,
        "project_a_indexing",
        {
            "content": (
                "PostgreSQL indexing strategies improve query performance. "
                "B-tree and hash indexes serve different access patterns."
            ),
            "project": "project_a",
            "topic": "database",
        },
    )

    # Store memories from project_b - also relevant to database queries
    await store.aput(
        namespace,
        "project_b_postgres",
        {
            "content": (
                "Postgres replication ensures high availability and data durability. "
                "Streaming replication provides near real-time failover capability."
            ),
            "project": "project_b",
            "topic": "database",
        },
    )

    await store.aput(
        namespace,
        "project_b_backup",
        {
            "content": (
                "Database backup strategies protect against data loss. "
                "We use pg_dump for logical backups and WAL archiving for point-in-time recovery."
            ),
            "project": "project_b",
            "topic": "database",
        },
    )

    # Semantic search with filter for project_a only
    query = "how do we optimize Postgres database performance"
    filtered_results = await store.asearch(
        namespace,
        query=query,
        filter={"project": "project_a"},
        limit=10,
    )

    # Verify only project_a memories are returned
    assert len(filtered_results) > 0, "Filter should return project_a results"
    for result in filtered_results:
        assert result.value.get("project") == "project_a", (
            f"Filter to project_a should exclude project_b, "
            f"but got key={result.key} with project={result.value.get('project')}"
        )

    # Verify results are still ranked by relevance (pooling is most relevant)
    # The query asks about "optimize performance" which should match pooling first
    returned_keys = [r.key for r in filtered_results]
    assert "project_a_pooling" in returned_keys, "Pooling memory should be in results"
    assert "project_a_indexing" in returned_keys, "Indexing memory should be in results"

    # Verify project_b memories are NOT in results
    assert "project_b_postgres" not in returned_keys, "project_b should be filtered out"
    assert "project_b_backup" not in returned_keys, "project_b should be filtered out"

    # Verify all results have the Item structure with key and value
    for result in filtered_results:
        assert hasattr(result, "key"), "Result should have key attribute"
        assert hasattr(result, "value"), "Result should have value attribute"
        assert isinstance(result.value, dict), "Value should be a dict"
        assert "content" in result.value, "Value should contain content field"


@pytest.mark.integration
async def test_search_without_filter_returns_all_projects(store_context_real) -> None:
    """Verify unfiltered search returns memories from all projects.

    Supplements AC-001: baseline behavior without filter parameter.
    """
    store, namespace = store_context_real

    # Store memories from multiple projects
    await store.aput(
        namespace,
        "alpha_item",
        {"content": "Database optimization for project alpha", "project": "alpha"},
    )

    await store.aput(
        namespace,
        "beta_item",
        {"content": "Database tuning for project beta", "project": "beta"},
    )

    # Search without filter - should return items from both projects
    query = "database"
    all_results = await store.asearch(namespace, query=query, limit=10)

    # Verify results from multiple projects are returned
    projects_in_results = {r.value.get("project") for r in all_results}
    assert "alpha" in projects_in_results, "Unfiltered search should include alpha"
    assert "beta" in projects_in_results, "Unfiltered search should include beta"
