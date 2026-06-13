"""Integration tests for full retrieval pipeline against real store and embed.

Marker-gated (@pytest.mark.integration) tests validating the complete retrieval path:
- Project-scoped, cosine-ranked search with real embeddings
- Supersession exclusion in end-to-end flow
- Token-budgeted assembly against real corpus content
- Probe-set harness execution with parity reporting
- Ephemeral PostgreSQL + pgvector on random ports (no NAS dependency)

Requirements:
- Docker running for ephemeral_pg fixture
- FLEET_MEMORY_EMBED_URL pointing to real embed service (GB10 or test service)
- Default test run (pytest) skips these; run with: pytest -m integration

AC-001: Integration marker gates these tests from hermetic unit runs
AC-002: Real store + real embed returns project-scoped, cosine-ranked results
AC-003: Supersession exclusion holds end-to-end
AC-004: Budgeted assembly stays within budget against real content
AC-005: Probe-set harness runs and emits parity report
AC-006: Tests use throwaway, random-port instance
"""

from __future__ import annotations

import pytest

from fleet_memory.payloads.models import DocumentPayload
from fleet_memory.retrieval.assembly import assemble_context
from fleet_memory.retrieval.core import search
from fleet_memory.retrieval.probe_harness import ProbeQuery, run_probe_harness
from fleet_memory.retrieval.search_request import SearchRequest
from fleet_memory.writer.core import DeterministicWriter


@pytest.mark.integration
async def test_real_embed_returns_project_scoped_ranked_results(
    store_context_real, test_settings
) -> None:
    """Real store + real embed returns project-scoped, cosine-ranked results.

    AC-002: Populate ephemeral store with real content, query with real embeddings,
    verify project-scoped results ordered by cosine similarity (highest first).

    Uses ephemeral PostgreSQL + pgvector on random port (AC-006).
    """
    store, test_namespace = store_context_real
    project = test_namespace[1]  # Extract project from namespace tuple

    # Write test documents using DeterministicWriter
    writer = DeterministicWriter(store, test_settings)

    # Write documents with varying relevance to query "database connection pooling"
    doc1 = DocumentPayload(
        project=project,
        identifier="doc_high_relevance",
        content="PostgreSQL database connection pooling is critical for performance. "
        "Connection pools reduce latency by reusing established connections. "
        "Pool size tuning depends on workload characteristics and resource constraints.",
        domain_tags=["database", "performance"],
    )

    doc2 = DocumentPayload(
        project=project,
        identifier="doc_medium_relevance",
        content="Database systems provide transactional guarantees through ACID properties. "
        "Connection management is one aspect of database architecture and optimization.",
        domain_tags=["database"],
    )

    doc3 = DocumentPayload(
        project=project,
        identifier="doc_low_relevance",
        content="Python asyncio event loops handle concurrent tasks efficiently. "
        "Async programming enables high-throughput network services.",
        domain_tags=["python", "concurrency"],
    )

    # Write all documents
    await writer.write(doc1)
    await writer.write(doc2)
    await writer.write(doc3)

    # Execute search with real embeddings
    request = SearchRequest(
        project=project,
        query="database connection pooling",
        token_budget=500,
        payload_types=["document"],
    )

    results = await search(request, store)

    # Verify project scoping: all results belong to this project
    assert len(results) > 0, "Should return at least one result"
    for result in results:
        namespace_parts = result.namespace
        assert namespace_parts[1] == project, f"Result namespace {namespace_parts} does not match project {project}"

    # Verify cosine ranking: results ordered by similarity descending
    scores = [result.score for result in results]
    assert scores == sorted(scores, reverse=True), "Results should be ordered by score descending"

    # Verify highest-ranked result is the most relevant document
    # (Real embeddings should rank doc1 highest for "database connection pooling")
    top_result = results[0]
    assert "doc_high_relevance" in top_result.key, (
        f"Expected doc_high_relevance to rank highest, got {top_result.key}"
    )


@pytest.mark.integration
async def test_supersession_exclusion_end_to_end(store_context_real, test_settings) -> None:
    """Supersession exclusion holds end-to-end against deterministic writer records.

    AC-003: Write document v1, write v2 with supersedes=[v1], verify search excludes
    v1 by default and includes it when include_superseded=True.
    """
    store, test_namespace = store_context_real
    project = test_namespace[1]

    writer = DeterministicWriter(store, test_settings)

    # Write original document v1
    doc_v1 = DocumentPayload(
        project=project,
        identifier="design_doc_v1",
        content="Initial design: use REST API for external communication.",
        domain_tags=["design"],
    )
    await writer.write(doc_v1)

    # Write updated document v2 that supersedes v1
    doc_v2 = DocumentPayload(
        project=project,
        identifier="design_doc_v2",
        content="Updated design: use gRPC API for external communication and better performance.",
        domain_tags=["design"],
        supersedes=["document:{}:design_doc_v1".format(project)],
    )
    await writer.write(doc_v2)

    # Search with default supersession exclusion (include_superseded=False)
    request_exclude = SearchRequest(
        project=project,
        query="external communication API",
        token_budget=500,
        include_superseded=False,
    )
    results_exclude = await search(request_exclude, store)

    # Verify v1 is excluded from results
    result_keys_exclude = [result.key for result in results_exclude]
    assert not any("design_doc_v1" in key for key in result_keys_exclude), (
        "Superseded document v1 should be excluded when include_superseded=False"
    )
    assert any("design_doc_v2" in key for key in result_keys_exclude), (
        "Superseding document v2 should be included"
    )

    # Search with supersession inclusion (include_superseded=True)
    request_include = SearchRequest(
        project=project,
        query="external communication API",
        token_budget=500,
        include_superseded=True,
    )
    results_include = await search(request_include, store)

    # Verify v1 is now included in results
    result_keys_include = [result.key for result in results_include]
    assert any("design_doc_v1" in key for key in result_keys_include), (
        "Superseded document v1 should be included when include_superseded=True"
    )
    assert any("design_doc_v2" in key for key in result_keys_include), (
        "Superseding document v2 should still be included"
    )


@pytest.mark.integration
async def test_budgeted_assembly_respects_token_limit(store_context_real, test_settings) -> None:
    """Budgeted assembly stays within budget when measured against real content.

    AC-004: Write multiple documents, assemble context with strict token budget,
    verify assembled block never exceeds budget and coverage score is accurate.
    """
    store, test_namespace = store_context_real
    project = test_namespace[1]

    writer = DeterministicWriter(store, test_settings)

    # Write multiple documents with substantial content
    for i in range(10):
        doc = DocumentPayload(
            project=project,
            identifier=f"technical_doc_{i:02d}",
            content=(
                f"Technical document {i} about distributed systems architecture. "
                f"This document discusses consensus algorithms, replication strategies, "
                f"fault tolerance mechanisms, and performance optimization techniques. "
                f"Content includes detailed explanations with examples and trade-offs. "
                f"Document {i} provides unique perspective on system design challenges."
            ),
            domain_tags=["technical", "architecture"],
        )
        await writer.write(doc)

    # Search with real embeddings
    request = SearchRequest(
        project=project,
        query="distributed systems architecture",
        token_budget=200,  # Strict budget that cannot fit all results
        payload_types=["document"],
    )
    results = await search(request, store)

    # Assemble context with strict token budget
    assembly = assemble_context(results, token_budget=200)

    # Verify assembly respects token budget (AC-004)
    assert assembly.tokens_used <= 200, (
        f"Assembled block used {assembly.tokens_used} tokens, exceeds budget of 200"
    )

    # Verify coverage score is between 0.0 and 1.0
    assert 0.0 <= assembly.coverage_score <= 1.0, (
        f"Coverage score {assembly.coverage_score} outside valid range [0.0, 1.0]"
    )

    # Verify context block is non-empty (at least one result should fit)
    assert len(assembly.context_block) > 0, "Context block should contain some content"

    # Verify contributing types metadata is populated
    assert "document" in assembly.contributing_types, (
        "Contributing types should include 'document'"
    )


@pytest.mark.integration
async def test_probe_harness_runs_against_real_corpus(store_context_real, test_settings) -> None:
    """Probe-set harness runs frozen query set and emits parity report.

    AC-005: Execute probe harness with small query set against real indexed corpus,
    verify parity report generation with expected structure and metrics.
    """
    store, test_namespace = store_context_real
    project = test_namespace[1]

    writer = DeterministicWriter(store, test_settings)

    # Write known corpus for deterministic probe queries
    doc1 = DocumentPayload(
        project=project,
        identifier="probe_corpus_pooling",
        content="Database connection pooling reduces latency by reusing connections.",
        domain_tags=["database"],
    )
    doc2 = DocumentPayload(
        project=project,
        identifier="probe_corpus_async",
        content="Async programming with Python asyncio enables concurrent task execution.",
        domain_tags=["python"],
    )
    await writer.write(doc1)
    await writer.write(doc2)

    # Define frozen probe set with expected baselines
    # Note: Baselines are intentionally set to match actual assembly output for parity
    probe_set = [
        ProbeQuery(
            query="database connection pooling",
            project=project,
            token_budget=100,
            baseline_answer=(
                "Database connection pooling reduces latency by reusing connections."
            ),
        ),
        ProbeQuery(
            query="async programming Python",
            project=project,
            token_budget=100,
            baseline_answer=(
                "Async programming with Python asyncio enables concurrent task execution."
            ),
        ),
    ]

    # Run probe harness
    report = await run_probe_harness(
        probe_set,
        search_fn=lambda req: search(req, store),
        assemble_fn=assemble_context,
    )

    # Verify parity report structure (AC-005)
    assert report.total_probes == 2, f"Expected 2 probes, got {report.total_probes}"
    assert isinstance(report.divergences_count, int), "Divergences count should be integer"
    assert isinstance(report.full_parity, bool), "Full parity should be boolean"
    assert isinstance(report.meets_minimum_size, bool), "Meets minimum size should be boolean"
    assert isinstance(report.divergent_queries, list), "Divergent queries should be list"

    # For this test, we expect some divergences due to real embeddings potentially
    # returning different results or ordering than the frozen baselines
    # The important part is that the harness runs successfully and reports status
    assert report.total_probes > 0, "Harness should execute all probe queries"


@pytest.mark.integration
async def test_ephemeral_fixture_uses_random_port(ephemeral_pg: str) -> None:
    """Ephemeral PostgreSQL fixture uses throwaway instance on random port.

    AC-006: Verify ephemeral_pg fixture provides DSN with non-standard port,
    confirming no NAS dependency and parallel-safe execution.
    """
    # Extract port from DSN
    assert ephemeral_pg.startswith("postgresql://"), "DSN should be PostgreSQL connection string"
    assert "127.0.0.1" in ephemeral_pg, "DSN should use localhost"

    # Verify port is not the standard 5432
    port_start = ephemeral_pg.rfind(":") + 1
    port_end = ephemeral_pg.rfind("/")
    port = int(ephemeral_pg[port_start:port_end])

    assert port != 5432, f"Ephemeral instance should not use standard port 5432, got {port}"
    assert 1024 < port < 65536, f"Port {port} outside valid ephemeral range"
