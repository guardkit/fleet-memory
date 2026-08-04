"""Unit tests for the manifest-driven reindex pipeline.

Covers the accounting invariant (walked == published + skipped + unparseable),
both arms of the within-run collision policy, and lessons preservation
(read-before-write).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fleet_memory.reindex.manifest import CorpusManifest, ManifestEntry
from fleet_memory.reindex.pipeline import RunReport, reindex_corpus
from fleet_memory.writer.identity import record_identity

# A live completed-task head (verbatim shape) parameterized per test
TASK_TEMPLATE = """---
id: {task_id}
title: {title}
status: completed
tags: [testing]
---

# {task_id}: {title}

Body prose.
"""


def _manifest() -> CorpusManifest:
    return CorpusManifest(
        schema_version=1,
        project="guardkit",
        entries=[
            ManifestEntry(
                kind="build_outcome",
                episode_type="build_outcome",
                directories=["tasks/completed"],
                owner="reindex",
                content_format="markdown",
            ),
        ],
    )


def _write_task(root: Path, relative: str, task_id: str, title: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TASK_TEMPLATE.format(task_id=task_id, title=title), encoding="utf-8")


class _CollectingPublisher:
    """Publisher stub recording payloads; returns None (published)."""

    def __init__(self) -> None:
        self.payloads = []

    async def __call__(self, payload):
        self.payloads.append(payload)
        return None


class TestAccountingInvariant:
    """walked == published + skipped + unparseable, always."""

    async def test_invariant_over_mixed_corpus(self, tmp_path: Path) -> None:
        _write_task(tmp_path, "tasks/completed/TASK-A.md", "TASK-A", "Task A")
        _write_task(tmp_path, "tasks/completed/2026-07/TASK-B.md", "TASK-B", "Task B")
        # Non-terminal status -> skipped
        (tmp_path / "tasks/completed/TASK-C.md").write_text(
            "---\nid: TASK-C\nstatus: backlog\n---\n\n# C\n", encoding="utf-8"
        )
        # No front-matter -> skipped
        (tmp_path / "tasks/completed/REPORT.md").write_text("# Report\n", encoding="utf-8")

        publisher = _CollectingPublisher()
        report = await reindex_corpus(tmp_path, _manifest(), publisher)

        assert report.walked_count == 4
        assert report.published_count == 2
        assert report.skipped_count == 2
        assert report.unparseable_count == 0
        assert report.walked_count == (
            report.published_count + report.skipped_count + report.unparseable_count
        )
        assert len(publisher.payloads) == 2

    async def test_every_skip_carries_path_and_reason(self, tmp_path: Path) -> None:
        (tmp_path / "tasks/completed").mkdir(parents=True)
        (tmp_path / "tasks/completed/REPORT.md").write_text("# Report\n", encoding="utf-8")

        report = await reindex_corpus(tmp_path, _manifest(), _CollectingPublisher())

        assert report.skipped == [
            {"path": "tasks/completed/REPORT.md", "reason": "no front-matter"}
        ]

    async def test_publisher_skip_reason_lands_in_skipped(self, tmp_path: Path) -> None:
        _write_task(tmp_path, "tasks/completed/TASK-A.md", "TASK-A", "Task A")

        async def skipping_publisher(payload):
            return "payload body 1 bytes exceeds MAX_EPISODE_BODY_BYTES (2)"

        report = await reindex_corpus(tmp_path, _manifest(), skipping_publisher)

        assert report.published_count == 0
        assert report.skipped_count == 1
        assert "MAX_EPISODE_BODY_BYTES" in report.skipped[0]["reason"]

    async def test_census_mode_counts_without_publishing(self, tmp_path: Path) -> None:
        """publisher=None (--dry-run): census only, nothing to connect to."""
        _write_task(tmp_path, "tasks/completed/TASK-A.md", "TASK-A", "Task A")

        report = await reindex_corpus(tmp_path, _manifest(), publisher=None)

        assert report.published_count == 1
        assert report.published_natural_keys == ["build_outcome:guardkit:TASK_A"]

    async def test_empty_corpus_completes_cleanly(self, tmp_path: Path) -> None:
        report = await reindex_corpus(tmp_path, _manifest(), _CollectingPublisher())
        assert report.walked_count == 0
        assert report.published_count == 0

    async def test_report_fields_serialize(self, tmp_path: Path) -> None:
        _write_task(tmp_path, "tasks/completed/TASK-A.md", "TASK-A", "Task A")
        report = await reindex_corpus(tmp_path, _manifest(), _CollectingPublisher())

        data = report.to_json_dict()
        # Round-trips through JSON (the run report file the audit reads)
        parsed = json.loads(json.dumps(data))
        assert parsed["published_natural_keys"] == ["build_outcome:guardkit:TASK_A"]
        assert parsed["per_kind_counts"] == {"build_outcome": 1}


class TestCollisionPolicy:
    """Within-run id collisions (40 duplicate ids live, 20 distinct tasks)."""

    async def test_same_id_same_title_collapses_deepest_path_wins(
        self, tmp_path: Path
    ) -> None:
        _write_task(tmp_path, "tasks/completed/TASK-012.md", "TASK-012", "Packaging")
        _write_task(
            tmp_path, "tasks/completed/2025-10/TASK-012.md", "TASK-012", "Packaging"
        )

        publisher = _CollectingPublisher()
        report = await reindex_corpus(tmp_path, _manifest(), publisher)

        # Exactly one published; the shallower copy is recorded as shadowed
        assert report.published_count == 1
        assert len(publisher.payloads) == 1
        assert (
            publisher.payloads[0].source_ref == "tasks/completed/2025-10/TASK-012.md"
        )
        shadowed = [s for s in report.skipped if "shadowed" in s["reason"]]
        assert len(shadowed) == 1
        assert shadowed[0]["path"] == "tasks/completed/TASK-012.md"
        assert "tasks/completed/2025-10/TASK-012.md" in shadowed[0]["reason"]

    async def test_same_id_different_title_skips_both(self, tmp_path: Path) -> None:
        """A curation ruling, never silent last-wins."""
        _write_task(tmp_path, "tasks/completed/TASK-003-parent.md", "TASK-003", "Parent")
        _write_task(
            tmp_path, "tasks/completed/TASK-003-scanner.md", "TASK-003", "Scanner"
        )

        publisher = _CollectingPublisher()
        report = await reindex_corpus(tmp_path, _manifest(), publisher)

        assert report.published_count == 0
        assert len(publisher.payloads) == 0
        collision_skips = [
            s for s in report.skipped if "id collision across distinct tasks" in s["reason"]
        ]
        assert len(collision_skips) == 2
        # The named reason carries both paths
        for skip in collision_skips:
            assert "tasks/completed/TASK-003-parent.md" in skip["reason"]
            assert "tasks/completed/TASK-003-scanner.md" in skip["reason"]

    async def test_collisions_preserve_invariant(self, tmp_path: Path) -> None:
        _write_task(tmp_path, "tasks/completed/TASK-1.md", "TASK-1", "Same")
        _write_task(tmp_path, "tasks/completed/2026-01/TASK-1.md", "TASK-1", "Same")
        _write_task(tmp_path, "tasks/completed/TASK-2a.md", "TASK-2", "Alpha")
        _write_task(tmp_path, "tasks/completed/TASK-2b.md", "TASK-2", "Beta")

        report = await reindex_corpus(tmp_path, _manifest(), _CollectingPublisher())

        assert report.walked_count == 4
        assert report.published_count == 1  # deepest TASK-1
        assert report.skipped_count == 3  # 1 shadowed + 2 distinct-title
        assert report.walked_count == (
            report.published_count + report.skipped_count + report.unparseable_count
        )


class FakeStore:
    """aget-only store stub returning pre-seeded rows keyed by (namespace, key)."""

    def __init__(self) -> None:
        self.rows: dict[tuple[tuple[str, ...], str], dict] = {}

    def seed(self, natural_key: str, value: dict) -> None:
        payload_type, project, _ = natural_key.split(":")
        namespace = ("fleet_memory", project, payload_type)
        self.rows[(namespace, str(record_identity(natural_key)))] = value

    async def aget(self, namespace: tuple[str, ...], key: str):
        value = self.rows.get((namespace, key))
        return SimpleNamespace(value=value) if value is not None else None


class TestLessonsPreservation:
    """Read-before-write: existing distilled lessons are never nulled."""

    @pytest.fixture
    def store(self) -> FakeStore:
        return FakeStore()

    async def test_existing_lessons_carried_forward(
        self, tmp_path: Path, store: FakeStore
    ) -> None:
        # Fixture task has NO lessons section; the store row carries prose
        _write_task(tmp_path, "tasks/completed/TASK-A.md", "TASK-A", "Task A")
        store.seed(
            "build_outcome:guardkit:TASK_A",
            {
                "content": json.dumps({"lessons": "Distilled: never trust mtime"}),
                "version": 2,
            },
        )

        publisher = _CollectingPublisher()
        await reindex_corpus(tmp_path, _manifest(), publisher, store=store)

        assert publisher.payloads[0].lessons == "Distilled: never trust mtime"

    async def test_fresh_lessons_win_over_stored(
        self, tmp_path: Path, store: FakeStore
    ) -> None:
        path = tmp_path / "tasks/completed/TASK-B.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\nid: TASK-B\ntitle: B\nstatus: completed\n---\n\n"
            "# B\n\n## Lessons\n\nFresh lesson from the file\n",
            encoding="utf-8",
        )
        store.seed(
            "build_outcome:guardkit:TASK_B",
            {"content": json.dumps({"lessons": "Old stored lesson"}), "version": 1},
        )

        publisher = _CollectingPublisher()
        await reindex_corpus(tmp_path, _manifest(), publisher, store=store)

        assert publisher.payloads[0].lessons == "Fresh lesson from the file"

    async def test_no_existing_row_leaves_lessons_none(
        self, tmp_path: Path, store: FakeStore
    ) -> None:
        _write_task(tmp_path, "tasks/completed/TASK-C.md", "TASK-C", "Task C")

        publisher = _CollectingPublisher()
        await reindex_corpus(tmp_path, _manifest(), publisher, store=store)

        assert publisher.payloads[0].lessons is None

    async def test_carried_lessons_keep_natural_key(
        self, tmp_path: Path, store: FakeStore
    ) -> None:
        """model_copy must not disturb the computed natural key."""
        _write_task(tmp_path, "tasks/completed/TASK-D.md", "TASK-D", "Task D")
        store.seed(
            "build_outcome:guardkit:TASK_D",
            {"content": json.dumps({"lessons": "kept"}), "version": 1},
        )

        publisher = _CollectingPublisher()
        report = await reindex_corpus(tmp_path, _manifest(), publisher, store=store)

        assert report.published_natural_keys == ["build_outcome:guardkit:TASK_D"]
        assert publisher.payloads[0].natural_key == "build_outcome:guardkit:TASK_D"


class TestRunReportDefaults:
    """RunReport dataclass shape."""

    def test_defaults(self) -> None:
        report = RunReport()
        assert report.walked_count == 0
        assert report.published_natural_keys == []
        assert report.skipped == []
        assert report.per_kind_counts == {}
