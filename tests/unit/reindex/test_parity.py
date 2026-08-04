"""Unit tests for the probe-set parity report generator.

The probe set (eval/probe_set.json) carries 16 probes and NO baseline answers
— the FEAT-MEM-05 freeze was declined deliberately. The old implementation
routed through run_probe_harness whose hit metric is exact equality vs
baseline: 0% hits BY CONSTRUCTION. These tests pin the corrected behavior:
direct search+assemble, retrieval-health hits, SKIPPED baseline diff, and the
candidate-baseline output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from fleet_memory.reindex.parity import (
    diff_against_baseline,
    generate_parity_report,
    load_probe_set,
    write_candidate_baseline,
)
from fleet_memory.retrieval.probe_harness import ProbeQuery

REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_PROBE_SET = REPO_ROOT / "eval" / "probe_set.json"


@dataclass
class MockAssemblyResult:
    """Mock AssemblyResult for testing."""

    context_block: str
    coverage_score: float
    contributing_types: set = field(default_factory=set)
    tokens_used: int = 0


def _search_fn(results=None):
    async def _search(request):
        return results or []

    return _search


def _assemble_fn(context_block: str, coverage_score: float):
    def _assemble(results, token_budget):
        return MockAssemblyResult(
            context_block=context_block, coverage_score=coverage_score
        )

    return _assemble


def _probes(count: int = 3) -> list[ProbeQuery]:
    return [
        ProbeQuery(
            query=f"query_{i}",
            project="guardkit",
            token_budget=2000,
            baseline_answer="",
        )
        for i in range(count)
    ]


class TestLoadProbeSet:
    """Loader tolerant of missing baseline_answer."""

    def test_loads_probes_without_baselines(self, tmp_path: Path) -> None:
        path = tmp_path / "probes.json"
        path.write_text(
            json.dumps(
                {
                    "probes": [
                        {"query": "What is X?", "project": "guardkit", "token_budget": 1500},
                        {"query": "What is Y?", "project": "guardkit"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        probes = load_probe_set(path)

        assert len(probes) == 2
        assert probes[0].baseline_answer == ""
        assert probes[0].token_budget == 1500
        assert probes[1].token_budget == 2000  # default

    def test_loads_the_live_probe_set(self) -> None:
        """The real eval/probe_set.json (16 probes, no baselines) must load."""
        if not LIVE_PROBE_SET.exists():
            pytest.skip("eval/probe_set.json not present")
        probes = load_probe_set(LIVE_PROBE_SET)
        assert len(probes) == 16
        assert all(probe.baseline_answer == "" for probe in probes)
        assert all(probe.project == "guardkit" for probe in probes)


class TestGenerateParityReport:
    """Direct search+assemble; hit = non-empty context AND coverage > 0."""

    async def test_hit_when_context_and_coverage(self) -> None:
        report = await generate_parity_report(
            _probes(3),
            _search_fn([object()]),
            _assemble_fn("some assembled context", 0.4),
        )
        assert report["total_probes"] == 3
        assert report["hits"] == 3
        assert report["hit_rate"] == 1.0
        assert all(row["hit"] for row in report["per_probe_results"])

    async def test_miss_when_context_empty(self) -> None:
        report = await generate_parity_report(
            _probes(2), _search_fn(), _assemble_fn("", 0.0)
        )
        assert report["hits"] == 0
        assert report["hit_rate"] == 0.0

    async def test_miss_when_coverage_zero_even_with_context(self) -> None:
        report = await generate_parity_report(
            _probes(1), _search_fn(), _assemble_fn("context", 0.0)
        )
        assert report["hits"] == 0

    async def test_baseline_diff_skipped_without_baselines(self) -> None:
        """No baselines -> named SKIPPED reason, never a fictitious 0% parity."""
        report = await generate_parity_report(
            _probes(2), _search_fn(), _assemble_fn("ctx", 0.5)
        )
        assert report["baseline_diff"].startswith("SKIPPED — ")
        assert "FEAT-MEM-05" in report["baseline_diff"]

    async def test_baseline_diff_computed_when_all_frozen(self) -> None:
        probes = [
            ProbeQuery(
                query="q", project="guardkit", token_budget=2000, baseline_answer="ctx"
            )
        ]
        report = await generate_parity_report(
            probes, _search_fn(), _assemble_fn("ctx", 0.5)
        )
        assert report["baseline_diff"] == "0 divergences vs frozen baseline"

    async def test_candidate_baseline_carries_answers(self) -> None:
        report = await generate_parity_report(
            _probes(2), _search_fn(), _assemble_fn("assembled answer", 0.5)
        )
        assert len(report["candidate_baseline"]) == 2
        for row in report["candidate_baseline"]:
            assert row["baseline_answer"] == "assembled answer"
            assert row["project"] == "guardkit"

    async def test_empty_probe_set(self) -> None:
        report = await generate_parity_report([], _search_fn(), _assemble_fn("", 0.0))
        assert report["total_probes"] == 0
        assert report["hit_rate"] == 0.0


class TestWriteCandidateBaseline:
    """Per-probe answers are written to the --out JSON."""

    async def test_writes_candidate_baseline_json(self, tmp_path: Path) -> None:
        report = await generate_parity_report(
            _probes(2), _search_fn(), _assemble_fn("frozen-me-later", 0.5)
        )
        out_path = tmp_path / "candidate.json"

        write_candidate_baseline(report, out_path)

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(data["probes"]) == 2
        assert data["probes"][0]["baseline_answer"] == "frozen-me-later"
        # The written shape is itself loadable as a probe set
        probes = load_probe_set(out_path)
        assert len(probes) == 2
        assert probes[0].baseline_answer == "frozen-me-later"


class TestBaselineDiff:
    """The operator-held frozen baseline: byte-diff with named divergences."""

    def _rows(self, answer: str) -> list[dict]:
        return [
            {
                "query": "q1",
                "project": "guardkit",
                "token_budget": 400,
                "baseline_answer": answer,
            }
        ]

    def test_identical_answers_zero_divergences(self) -> None:
        diff = diff_against_baseline(self._rows("same"), self._rows("same"))
        assert diff["divergence_count"] == 0
        assert diff["compared"] == 1

    def test_changed_answer_named(self) -> None:
        diff = diff_against_baseline(self._rows("new"), self._rows("old"))
        assert diff["divergence_count"] == 1
        assert "answer diverged" in diff["divergences"][0]

    def test_probe_missing_from_baseline_named(self) -> None:
        diff = diff_against_baseline(self._rows("a"), [])
        assert diff["divergence_count"] == 1
        assert "not in baseline" in diff["divergences"][0]

    def test_baseline_probe_missing_from_run_named(self) -> None:
        diff = diff_against_baseline([], self._rows("a"))
        assert diff["divergence_count"] == 1
        assert "missing from run" in diff["divergences"][0]
