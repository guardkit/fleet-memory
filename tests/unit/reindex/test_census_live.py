"""LIVE-CORPUS CENSUS TEST — the test class that would have caught
"70,903 processed, 0 published".

Runs the real pipeline in census mode (publisher=None, no store/NATS) over the
ACTUAL guardkit checkout named by GUARDKIT_ROOT. Corpus facts (2026-08 census):
2,286 md files under tasks/completed, 1,675 with front-matter, 1,561 terminal,
1,545 terminal-with-id; 40 duplicate-id files live, 20 ids across distinct
tasks. The walker must stay inside tasks/completed (walked < 3,000 — the whole
checkout with .guardkit/worktrees is 63,683+ files) and the classifier must
actually publish (publishable > 1,400 — the old front-matter type contract
published ZERO).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fleet_memory.reindex.pipeline import reindex_corpus

GUARDKIT_ROOT = os.environ.get("GUARDKIT_ROOT", "")

pytestmark = pytest.mark.skipif(
    not GUARDKIT_ROOT or not Path(GUARDKIT_ROOT).is_dir(),
    reason="GUARDKIT_ROOT unset or not a directory (live-corpus census needs the real checkout)",
)


@pytest.fixture(scope="module")
def census_report():
    # Module-scoped: one walk of 2,286 real files serves every assertion
    import asyncio

    from fleet_memory.reindex.manifest import load_manifest

    manifest = load_manifest(
        Path(__file__).resolve().parents[2] / "fixtures" / "corpus_manifest.json"
    )
    return asyncio.run(
        reindex_corpus(Path(GUARDKIT_ROOT), manifest, publisher=None, store=None)
    )


class TestLiveCorpusCensus:
    """Census over the real guardkit tasks/completed corpus."""

    def test_walked_stays_inside_reindex_roots(self, census_report) -> None:
        """Walked < 3,000: the walker never inflates into .guardkit/worktrees."""
        assert census_report.walked_count < 3000
        assert census_report.walked_count > 2000  # the corpus is really there

    def test_publishable_count_over_1400(self, census_report) -> None:
        """Publishable > 1,400: the classifier matches corpus reality."""
        assert census_report.published_count > 1400

    def test_accounting_invariant_holds_at_scale(self, census_report) -> None:
        assert census_report.walked_count == (
            census_report.published_count
            + census_report.skipped_count
            + census_report.unparseable_count
        )

    def test_every_skip_names_its_reason(self, census_report) -> None:
        assert all(row["reason"] for row in census_report.skipped)

    def test_natural_keys_are_store_safe(self, census_report) -> None:
        """Every published identifier satisfies IDENTIFIER_PATTERN (dotted ids
        sanitized, none poised to DLQ)."""
        import re

        pattern = re.compile(r"^build_outcome:guardkit:[A-Za-z0-9_]+$")
        for natural_key in census_report.published_natural_keys:
            assert pattern.match(natural_key), natural_key
