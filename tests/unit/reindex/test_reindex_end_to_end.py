"""End-to-end reindex tests over a mini fixture repo with stub store + broker.

Wires the REAL chain: pipeline -> ReindexPublisher (stub JetStream) -> relay
envelope -> registry payload -> DeterministicWriter -> stub store. Covers the
three corpus-reality invariants:
- the walker yields only tasks/completed (a .guardkit/worktrees decoy full of
  .md files is never read),
- a second run is a zero-write (aput spy: content-hash no-op),
- an export-shaped pre-seeded row (source_ref "falkordb:...") version-bumps
  rather than duplicating.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.reindex.manifest import CorpusManifest, ManifestEntry
from fleet_memory.reindex.pipeline import reindex_corpus
from fleet_memory.reindex.publisher import ReindexPublisher
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import record_identity

# Verbatim head of a live completed task (guardkit/tasks/completed/2026-07/
# TASK-FIX-RESUMEVENV01-resume-venv-resolution.md) — reused as the mini repo's
# task content so the end-to-end chain runs over a real shape.
FIXTURE_TASK = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "corpus"
    / "tasks"
    / "completed"
    / "2026-07"
    / "TASK-FIX-RESUMEVENV01-resume-venv-resolution.md"
)


class SpyStore:
    """In-memory store with aget/aput spies (AsyncPostgresStore surface)."""

    def __init__(self) -> None:
        self.rows: dict[tuple[tuple[str, ...], str], dict] = {}
        self.aput_calls: list[tuple[tuple[str, ...], str]] = []

    async def aget(self, namespace: tuple[str, ...], key: str):
        value = self.rows.get((namespace, key))
        if value is None:
            return None
        return SimpleNamespace(value=value)

    async def aput(self, namespace: tuple[str, ...], key: str, value: dict) -> None:
        self.aput_calls.append((namespace, key))
        self.rows[(namespace, key)] = value

    async def asearch(self, namespace, **kwargs):  # supersession helper surface
        return []


class StubJetStream:
    """Broker stub capturing JetStream publishes and driving the writer."""

    def __init__(self, writer: DeterministicWriter) -> None:
        self.writer = writer
        self.published: list[tuple[str, dict]] = []

    async def publish(self, subject: str, body: bytes, headers=None) -> None:
        envelope_dict = json.loads(body)
        self.published.append((subject, envelope_dict))
        # Relay path: envelope -> schema -> registry payload -> writer
        episode = MemoryEpisodeV1(**envelope_dict)
        model_class = get_model_for_type(episode.payload_type)
        payload = model_class(**json.loads(episode.body))
        await self.writer.write(
            payload, episode_meta={"episode_type": episode.episode_type}
        )


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


def _build_mini_repo(root: Path) -> None:
    """Mini fixture repo: one real task + a .guardkit/worktrees decoy."""
    task_dir = root / "tasks" / "completed" / "2026-07"
    task_dir.mkdir(parents=True)
    (task_dir / FIXTURE_TASK.name).write_text(
        FIXTURE_TASK.read_text(encoding="utf-8"), encoding="utf-8"
    )

    # Decoy: the live checkout carries 63k files under .guardkit/worktrees
    decoy = root / ".guardkit" / "worktrees" / "FEAT-X" / "tasks" / "completed"
    decoy.mkdir(parents=True)
    for i in range(10):
        (decoy / f"TASK-DECOY-{i}.md").write_text(
            f"---\nid: TASK-DECOY-{i}\nstatus: completed\n---\n\n# Decoy {i}\n",
            encoding="utf-8",
        )


def _publisher_over(js: StubJetStream) -> ReindexPublisher:
    settings = MagicMock()
    settings.publish_nats_url = "nats://stub:4222"
    publisher = ReindexPublisher(settings)
    publisher._js = js
    return publisher


NATURAL_KEY = "build_outcome:guardkit:TASK_FIX_RESUMEVENV01"
NAMESPACE = ("fleet_memory", "guardkit", "build_outcome")


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    _build_mini_repo(tmp_path)
    return tmp_path


class TestEndToEnd:
    """pipeline -> publisher -> relay shape -> writer -> store."""

    async def test_walker_yields_only_tasks_completed(self, mini_repo: Path) -> None:
        store = SpyStore()
        writer = DeterministicWriter(store=store, settings=MagicMock())
        js = StubJetStream(writer)

        report = await reindex_corpus(
            mini_repo, _manifest(), _publisher_over(js).publish, store=store
        )

        # The decoy's 10 files were never walked, let alone published
        assert report.walked_count == 1
        assert report.published_count == 1
        assert [subject for subject, _ in js.published] == [
            "memory.episode.guardkit.build_outcome"
        ]
        assert report.published_natural_keys == [NATURAL_KEY]

    async def test_second_run_is_zero_write(self, mini_repo: Path) -> None:
        """Content-hash no-op: the second run calls aput ZERO times."""
        store = SpyStore()
        writer = DeterministicWriter(store=store, settings=MagicMock())
        js = StubJetStream(writer)
        publish = _publisher_over(js).publish

        await reindex_corpus(mini_repo, _manifest(), publish, store=store)
        writes_after_first = len(store.aput_calls)
        assert writes_after_first == 1

        await reindex_corpus(mini_repo, _manifest(), publish, store=store)

        assert len(store.aput_calls) == writes_after_first  # zero new writes
        stored = store.rows[(NAMESPACE, str(record_identity(NATURAL_KEY)))]
        assert stored["version"] == 1

    async def test_export_seeded_row_version_bumps_not_duplicates(
        self, mini_repo: Path
    ) -> None:
        """A pre-seeded export row (source_ref "falkordb:...") shares the natural
        key: the re-publish version-bumps the SAME record and carries its
        lessons forward — never a second row."""
        store = SpyStore()
        writer = DeterministicWriter(store=store, settings=MagicMock())
        js = StubJetStream(writer)

        # Export-shaped pre-seeded row (FEAT-MEM-09 FalkorDB migration shape)
        seeded_payload = {
            "project": "guardkit",
            "identifier": "TASK_FIX_RESUMEVENV01",
            "status": "success",
            "duration_seconds": 0,
            "task_id": "TASK_FIX_RESUMEVENV01",
            "lessons": "Distilled by the export: probe both venv locations",
            "approach": None,
            "domain_tags": ["task"],
            "source_ref": "falkordb:guardkit_task_outcomes",
            "version": 1,
            "supersedes": [],
            "natural_key": NATURAL_KEY,
        }
        store_key = str(record_identity(NATURAL_KEY))
        store.rows[(NAMESPACE, store_key)] = {
            "content": json.dumps(seeded_payload, sort_keys=True),
            "content_hash": "export-era-hash",
            "version": 3,
            "payload_type": "build_outcome",
            "natural_key": NATURAL_KEY,
            "project": "guardkit",
            "identifier": "TASK_FIX_RESUMEVENV01",
        }

        report = await reindex_corpus(
            mini_repo, _manifest(), _publisher_over(js).publish, store=store
        )

        assert report.published_count == 1

        # Exactly ONE row for the natural key — version bumped, not duplicated
        matching_rows = [
            key for key in store.rows if key == (NAMESPACE, store_key)
        ]
        assert len(matching_rows) == 1
        assert len(store.rows) == 1
        stored = store.rows[(NAMESPACE, store_key)]
        assert stored["version"] == 4

        # Lessons preservation: the fixture file has no lessons section, so the
        # export's distilled lessons rode forward into the new version
        stored_payload = json.loads(stored["content"])
        assert (
            stored_payload["lessons"]
            == "Distilled by the export: probe both venv locations"
        )
