"""Shared corpus/manifest helpers for the reindex integration tests.

The reindex pipeline is manifest-driven: it walks ONLY the manifest's
reindex-owned roots (``tasks/completed`` in the guardkit manifest), publishes a
file only when its front-matter carries an ``id`` and a terminal status, and
parses every publishable file into a ``BuildOutcomePayload`` for project
``guardkit``. Harvest-owned directories (``docs/adr`` and friends) are never
walked, so these helpers build corpora under ``tasks/completed`` only.

The manifest is the real exporter output checked in at
``tests/fixtures/corpus_manifest.json`` (the same file the unit tests load), and
the task template mirrors the head of a live completed task
(``tests/fixtures/corpus/tasks/completed/2026-07/
TASK-FIX-RESUMEVENV01-resume-venv-resolution.md``) with a lessons section — the
one piece of body prose the parser carries into the stored payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fleet_memory.reindex.manifest import CorpusManifest, load_manifest
from fleet_memory.reindex.parsers import sanitize_identifier

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "corpus_manifest.json"

# Every parsed task publishes into this namespace (project is the literal "guardkit")
BUILD_OUTCOME_NAMESPACE = ("fleet_memory", "guardkit", "build_outcome")

# Live completed-task head shape (see module docstring), parameterized per test
TASK_TEMPLATE = """---
id: {task_id}
title: {title}
status: completed
task_type: bugfix
priority: high
created: 2026-07-05
closed: 2026-07-09
tags: [{tags}]
---

# {task_id}: {title}

## Description

Body prose describing the change.

## Lessons Learned

{lessons}

## Files Changed

| File | Change |
|------|--------|
| `src/example.py` | Example change |
"""


def load_guardkit_manifest() -> CorpusManifest:
    """Load and validate the checked-in guardkit corpus manifest."""
    return load_manifest(MANIFEST_PATH)


def unique_task_id(label: str) -> str:
    """A guardkit-style task id unique to this test run.

    The ephemeral database is shared by the whole session and every parsed task
    lands in the same ``guardkit/build_outcome`` namespace, so ids carry a random
    suffix to keep tests from seeing each other's records.
    """
    return f"TASK-RIT-{label}-{uuid4().hex[:8]}"


def write_task(
    corpus_root: Path,
    task_id: str,
    *,
    title: str = "Reindex integration task",
    lessons: str = "Probe both venv locations before falling back.",
    tags: str = "autobuild, reindex",
    relative_dir: str = "tasks/completed/2026-07",
) -> Path:
    """Write a publishable completed task file under a reindex-owned root.

    Returns:
        Path of the written task file
    """
    path = corpus_root / relative_dir / f"{task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        TASK_TEMPLATE.format(task_id=task_id, title=title, lessons=lessons, tags=tags),
        encoding="utf-8",
    )
    return path


def natural_key_for(task_id: str) -> str:
    """Natural key the pipeline mints for a guardkit task id."""
    return f"build_outcome:guardkit:{sanitize_identifier(task_id)}"


def stored_payload(record: Any) -> dict[str, Any]:
    """Decode the payload JSON the writer stores in a record's content field."""
    return json.loads(record.value["content"])


async def records_for_identifier(store: Any, task_id: str) -> list[Any]:
    """Every stored build_outcome record carrying this task's identifier.

    Filters on the stored identifier, not the store key, so a duplicate written
    under a different key would be counted too.
    """
    return await store.asearch(
        BUILD_OUTCOME_NAMESPACE,
        filter={"identifier": sanitize_identifier(task_id)},
        limit=100,
    )


class CountingStore:
    """Thin proxy over a real store that counts ``aput`` calls.

    Used to prove a run wrote nothing: the writer's content-hash no-op skips
    ``aput`` entirely.
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self.aput_calls: list[tuple[tuple[str, ...], str]] = []

    async def aput(self, namespace: tuple[str, ...], key: str, value: dict, *args, **kwargs):
        self.aput_calls.append((namespace, key))
        return await self._store.aput(namespace, key, value, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)
