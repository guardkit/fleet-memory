"""Probe-set parity report generator for re-index validation.

Runs the frozen probe set (eval/probe_set.json — 16 probes, NONE carrying
baseline answers: the FEAT-MEM-05 baseline freeze was declined deliberately)
directly through search + assembly and reports a retrieval-health hit per probe.

The old implementation routed through run_probe_harness, whose hit metric is
exact string equality against baseline_answer — with no baselines that is 0%
hits BY CONSTRUCTION, a fiction detector reporting fiction. Here a hit means
the store actually answered: non-empty context_block and coverage_score > 0.

The report also writes every assembled answer to a candidate-baseline JSON so
an operator can freeze real baselines later (--out).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fleet_memory.retrieval.probe_harness import ProbeQuery
from fleet_memory.retrieval.search_request import SearchRequest

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# Named reason the baseline diff is skipped while the probe set carries no baselines
BASELINE_DIFF_SKIPPED = (
    "SKIPPED — probe set carries no frozen baseline answers "
    "(the FEAT-MEM-05 baseline freeze was declined deliberately)"
)


def load_probe_set(path: Path | str) -> list[ProbeQuery]:
    """Load the probe set JSON, tolerant of missing baseline_answer.

    eval/probe_set.json has 16 probes and none carry baselines; a loader that
    required baseline_answer would refuse the only probe set we have.

    Args:
        path: Path to the probe set JSON ({"probes": [{query, project, ...}]})

    Returns:
        List of ProbeQuery (baseline_answer defaults to "")
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    probes: list[ProbeQuery] = []
    for row in data.get("probes", []):
        probes.append(
            ProbeQuery(
                query=row["query"],
                project=row["project"],
                token_budget=row.get("token_budget", 2000),
                baseline_answer=row.get("baseline_answer", ""),
                payload_types=row.get("payload_types"),
                domain_tags=row.get("domain_tags"),
            )
        )
    return probes


async def generate_parity_report(
    probe_set: list[ProbeQuery],
    search_fn: Callable[[SearchRequest], Awaitable[list[Any]]],
    assemble_fn: Callable[[list[Any], int], Any],
) -> dict[str, Any]:
    """Generate a retrieval-health parity report for the given probe set.

    Runs search + assembly DIRECTLY per probe (NOT run_probe_harness — its hit
    metric is exact-equality vs baseline, 0% by construction with no baselines).
    A hit is a non-empty context_block with coverage_score > 0.

    Args:
        probe_set: List of ProbeQuery objects
        search_fn: Async function that executes search (from core.search)
        assemble_fn: Function that assembles context (from assembly.assemble_context)

    Returns:
        Report dict:
        {
            "total_probes": int,
            "hits": int,
            "hit_rate": float,          # 0.0-1.0
            "baseline_diff": str,        # "SKIPPED — <reason>" without baselines
            "per_probe_results": [{"query": str, "hit": bool}, ...],
            "candidate_baseline": [      # written to --out as a future frozen baseline
                {"query", "project", "token_budget", "baseline_answer"}, ...
            ],
        }
    """
    per_probe_results: list[dict[str, Any]] = []
    candidate_baseline: list[dict[str, Any]] = []
    hits = 0

    for probe in probe_set:
        request = SearchRequest(
            project=probe.project,
            query=probe.query,
            token_budget=probe.token_budget,
            payload_types=probe.payload_types or [],
            domain_tags=probe.domain_tags or [],
        )

        search_results = await search_fn(request)
        assembly_result = assemble_fn(search_results, probe.token_budget)

        hit = bool(assembly_result.context_block) and assembly_result.coverage_score > 0
        if hit:
            hits += 1

        per_probe_results.append({"query": probe.query, "hit": hit})
        candidate_baseline.append(
            {
                "query": probe.query,
                "project": probe.project,
                "token_budget": probe.token_budget,
                "baseline_answer": assembly_result.context_block,
            }
        )

    total_probes = len(probe_set)
    hit_rate = hits / total_probes if total_probes > 0 else 0.0

    if all(probe.baseline_answer for probe in probe_set) and total_probes > 0:
        divergences = sum(
            1
            for probe, candidate in zip(probe_set, candidate_baseline)
            if candidate["baseline_answer"] != probe.baseline_answer
        )
        baseline_diff: str = f"{divergences} divergences vs frozen baseline"
    else:
        baseline_diff = BASELINE_DIFF_SKIPPED

    return {
        "total_probes": total_probes,
        "hits": hits,
        "hit_rate": hit_rate,
        "baseline_diff": baseline_diff,
        "per_probe_results": per_probe_results,
        "candidate_baseline": candidate_baseline,
    }


def write_candidate_baseline(report: dict[str, Any], out_path: Path | str) -> None:
    """Write the report's per-probe answers as a candidate-baseline JSON.

    Args:
        report: Report dict from generate_parity_report
        out_path: Destination path (--out)
    """
    payload = {"probes": report.get("candidate_baseline", [])}
    Path(out_path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def diff_against_baseline(
    candidate_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diff current answers against a frozen baseline (operator-held file).

    The baseline file is the SAME shape --out writes (query/project/
    token_budget/baseline_answer rows). It lives OUTSIDE the repo by rule:
    answers embed store content, and this repository is public (DF-008 —
    internal content structurally unable to leak; the operator freezes the
    candidate at a local path and passes it back via --baseline).

    A probe diverges when its current answer differs byte-wise from the
    frozen one; probes present on only one side are named, never ignored.
    """
    key = lambda r: (r["query"], r["project"], r["token_budget"])  # noqa: E731
    frozen = {key(r): r["baseline_answer"] for r in baseline_rows}
    current = {key(r): r["baseline_answer"] for r in candidate_rows}

    divergences: list[str] = []
    for k, answer in current.items():
        if k not in frozen:
            divergences.append(f"probe not in baseline: {k[0]!r}")
        elif frozen[k] != answer:
            divergences.append(f"answer diverged: {k[0]!r}")
    for k in frozen:
        if k not in current:
            divergences.append(f"baseline probe missing from run: {k[0]!r}")

    return {
        "compared": len(current),
        "divergence_count": len(divergences),
        "divergences": divergences,
    }
