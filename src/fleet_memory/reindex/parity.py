"""Probe-set parity report generator for re-index validation (TASK-RIP-008).

Generates a JSON report of retrieval parity against the frozen probe set,
reusing the existing probe harness from FEAT-MEM-05. This report is used
to validate that the re-indexed corpus maintains retrieval quality.

Producer: TASK-RIP-008
Consumer: TASK-RIP-011 (operator verification)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fleet_memory.retrieval.probe_harness import ProbeQuery, run_probe_harness


async def generate_parity_report(
    probe_set: list[ProbeQuery],
    search_fn: Callable[[Any], Awaitable[list[Any]]],
    assemble_fn: Callable[[list[Any], int], Any],
) -> dict[str, Any]:
    """Generate a parity report for the given probe set.

    Runs the frozen probe set against the re-indexed store using the existing
    probe harness and generates a JSON-serializable report with per-probe
    hit/miss status and aggregate parity metrics.

    Args:
        probe_set: List of ProbeQuery objects with queries and baselines
        search_fn: Async function that executes search (from core.search)
        assemble_fn: Function that assembles context (from assembly.assemble_context)

    Returns:
        Dictionary with the following structure:
        {
            "total_probes": int,
            "divergences_count": int,
            "full_parity": bool,
            "aggregate_parity": float,  # 0.0 to 1.0
            "per_probe_results": [
                {
                    "query": str,
                    "hit": bool
                },
                ...
            ]
        }

    Example:
        >>> from fleet_memory.retrieval.core import search
        >>> from fleet_memory.retrieval.assembly import assemble_context
        >>> probes = load_probe_set()
        >>> async with async_store_context(settings) as store:
        ...     report = await generate_parity_report(
        ...         probes,
        ...         lambda req: search(req, store),
        ...         assemble_context
        ...     )
        >>> print(f"Parity: {report['aggregate_parity']:.2%}")
    """
    # Reuse the existing probe harness from FEAT-MEM-05
    harness_report = await run_probe_harness(probe_set, search_fn, assemble_fn)

    # Calculate aggregate parity as percentage (hits / total)
    if harness_report.total_probes > 0:
        hits = harness_report.total_probes - harness_report.divergences_count
        aggregate_parity = hits / harness_report.total_probes
    else:
        aggregate_parity = 0.0

    # Build per-probe results list
    per_probe_results = []
    divergent_set = set(harness_report.divergent_queries)

    for probe in probe_set:
        per_probe_results.append(
            {
                "query": probe.query,
                "hit": probe.query not in divergent_set,
            }
        )

    # Return JSON-serializable report
    return {
        "total_probes": harness_report.total_probes,
        "divergences_count": harness_report.divergences_count,
        "full_parity": harness_report.full_parity,
        "aggregate_parity": aggregate_parity,
        "per_probe_results": per_probe_results,
    }
