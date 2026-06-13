"""Probe-set evaluation harness for retrieval parity validation.

Runs a frozen set of probe queries against the retrieval system and compares
results to recorded baselines, generating a parity report to detect divergence.

This harness is the acceptance instrument for FEAT-MEM-05 and will be reused
by FEAT-MEM-07/08 for re-indexing validation.

Producer: TASK-RA-005
Consumer: FEAT-MEM-07/08 (re-index validation)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fleet_memory.retrieval.search_request import SearchRequest

# Minimum probe set size required to satisfy the retrieval-parity gate
MIN_PROBE_SET_SIZE = 15

# Parity tolerance: number of divergences allowed for full parity
# Default: 0 (zero-divergence = full parity)
# ASSUM-007: This may change to OD-2 tolerance later (one-line change)
PARITY_TOLERANCE = 0


@dataclass
class ProbeQuery:
    """A single probe query with its expected baseline answer.

    Attributes:
        query: The search query string
        project: Project scope for the query
        token_budget: Maximum tokens for assembled context
        baseline_answer: The expected/recorded answer to compare against
        payload_types: Optional payload type filters
        domain_tags: Optional domain tag filters
    """

    query: str
    project: str
    token_budget: int
    baseline_answer: str
    payload_types: list[str] | None = None
    domain_tags: list[str] | None = None


@dataclass
class ParityReport:
    """Report of probe harness execution and parity status.

    Attributes:
        total_probes: Number of probes executed
        divergences_count: Number of probes whose results diverged from baseline
        full_parity: Whether full parity was achieved (divergences <= tolerance)
        meets_minimum_size: Whether probe set meets minimum size requirement
        divergent_queries: List of query strings that diverged from baseline
    """

    total_probes: int
    divergences_count: int
    full_parity: bool
    meets_minimum_size: bool
    divergent_queries: list[str]


async def run_probe_harness(
    probe_set: list[ProbeQuery],
    search_fn: Callable[[SearchRequest], Awaitable[list[Any]]],
    assemble_fn: Callable[[list[Any], int], Any],
) -> ParityReport:
    """Run probe-set evaluation and generate parity report.

    Executes each probe query through the full retrieval pipeline (search +
    assembly) and compares the assembled context to the recorded baseline.
    Any divergence from baseline is flagged.

    Args:
        probe_set: List of ProbeQuery objects with queries and baselines
        search_fn: Async function that executes search (from core.search)
        assemble_fn: Function that assembles context (from assembly.assemble_context)

    Returns:
        ParityReport with execution summary and parity status

    Example:
        >>> from fleet_memory.retrieval.core import search
        >>> from fleet_memory.retrieval.assembly import assemble_context
        >>> probes = load_probe_set()  # Load from frozen fixtures
        >>> async with async_store_context(settings) as store:
        ...     report = await run_probe_harness(
        ...         probes,
        ...         lambda req: search(req, store),
        ...         assemble_context
        ...     )
        >>> print(f"Parity: {report.full_parity}, Divergences: {report.divergences_count}")
    """
    total_probes = len(probe_set)
    divergences_count = 0
    divergent_queries: list[str] = []

    # Execute each probe query
    for probe in probe_set:
        # Build SearchRequest for this probe
        request = SearchRequest(
            project=probe.project,
            query=probe.query,
            token_budget=probe.token_budget,
            payload_types=probe.payload_types or [],
            domain_tags=probe.domain_tags or [],
        )

        # Execute search
        search_results = await search_fn(request)

        # Assemble context from search results
        assembly_result = assemble_fn(search_results, probe.token_budget)

        # Compare assembled context to baseline
        actual_answer = assembly_result.context_block
        expected_answer = probe.baseline_answer

        # Check for divergence
        if actual_answer != expected_answer:
            divergences_count += 1
            divergent_queries.append(probe.query)

    # Check if probe set meets minimum size requirement
    meets_minimum_size = total_probes >= MIN_PROBE_SET_SIZE

    # Check if full parity achieved (divergences within tolerance)
    full_parity = divergences_count <= PARITY_TOLERANCE

    return ParityReport(
        total_probes=total_probes,
        divergences_count=divergences_count,
        full_parity=full_parity,
        meets_minimum_size=meets_minimum_size,
        divergent_queries=divergent_queries,
    )
