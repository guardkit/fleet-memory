"""Integration tests for re-index idempotency, concurrency, and convergence.

Marker-gated (@pytest.mark.integration) tests running the manifest-driven
reindex pipeline (walk -> classify -> parse -> publish) into DeterministicWriter
against ephemeral PostgreSQL + pgvector (hermetic, no NATS dependency). The
corpus is completed guardkit tasks under the reindex-owned ``tasks/completed``
root, loaded with the real guardkit corpus manifest:

- Second run over unchanged corpus creates or modifies no stored record (AC-001)
- Re-indexing after editing a source document updates its record, no duplicate (AC-002)
- Two concurrent re-index runs converge to exactly one record per natural key (AC-003)
- Publishing the same parsed document twice yields exactly one record (AC-004)

Requirements:
- Docker running for ephemeral_pg fixture
- Default test run (pytest) skips these via @pytest.mark.integration
- Run with: pytest -m integration tests/integration/reindex/

Covers TASK-RIP-010 integration scenarios AC-001 through AC-004.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fleet_memory.embed import make_fake_embed
from fleet_memory.payloads.models import ADRPayload
from fleet_memory.reindex.pipeline import reindex_corpus
from fleet_memory.store import async_store_context
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import record_identity
from tests.integration.reindex.corpus_support import (
    BUILD_OUTCOME_NAMESPACE,
    CountingStore,
    load_guardkit_manifest,
    natural_key_for,
    records_for_identifier,
    stored_payload,
    unique_task_id,
    write_task,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fleet_memory.payloads.base import BasePayload


# ============================================================================
# Test Fixtures
# ============================================================================


def _make_adr_payload(**overrides) -> ADRPayload:
    """Factory for ADRPayload test instances with sensible defaults."""
    defaults = {
        "project": "reindex_integration_test",
        "identifier": "ADR_001",
        "source_ref": "integration/reindex/adr/ADR_001.md",
        "decision": "Use PostgreSQL for persistence layer",
        "status": "accepted",
        "version": 1,
    }
    defaults.update(overrides)
    return ADRPayload(**defaults)


@pytest.fixture
def make_adr_payload() -> Callable[..., ADRPayload]:
    """Fixture providing ADRPayload factory for integration tests."""
    return _make_adr_payload


# ============================================================================
# AC-001: Second run over unchanged corpus is no-op
# ============================================================================


@pytest.mark.integration
async def test_second_run_is_noop(test_settings, ephemeral_pg, tmp_path: Path):
    """Second run over an unchanged corpus creates or modifies no stored record.

    The first run publishes a completed task (version 1). The second run over the
    same files publishes it again, and the writer's content-hash check turns that
    into a no-op: zero store writes, same version, same content hash, same
    updated_at.

    Acceptance criteria AC-001.
    """
    manifest = load_guardkit_manifest()
    task_id = unique_task_id("NOOP")
    corpus_root = tmp_path / "corpus"
    write_task(corpus_root, task_id)

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as real_store:
        store = CountingStore(real_store)
        writer = DeterministicWriter(store, test_settings)

        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        key = str(record_identity(natural_key_for(task_id)))

        # First run: the task really publishes and is stored at version 1
        first_report = await reindex_corpus(
            corpus_root, manifest, direct_publisher, store=store
        )
        assert first_report.walked_count == 1
        assert first_report.published_count == 1, first_report.to_json_dict()
        assert first_report.published_natural_keys == [natural_key_for(task_id)]
        assert len(store.aput_calls) == 1

        first_record = await store.aget(BUILD_OUTCOME_NAMESPACE, key)
        assert first_record is not None, "First run should create the record"
        assert first_record.value["version"] == 1

        # Second run over the unchanged corpus
        writes_before = len(store.aput_calls)
        second_report = await reindex_corpus(
            corpus_root, manifest, direct_publisher, store=store
        )
        assert second_report.published_count == 1, second_report.to_json_dict()

        # Nothing written, nothing modified
        assert len(store.aput_calls) == writes_before, (
            f"Second run wrote to the store: {store.aput_calls[writes_before:]}"
        )
        second_record = await store.aget(BUILD_OUTCOME_NAMESPACE, key)
        assert second_record is not None
        assert second_record.value["version"] == first_record.value["version"]
        assert second_record.value["content_hash"] == first_record.value["content_hash"]
        assert second_record.updated_at == first_record.updated_at
        assert len(await records_for_identifier(store, task_id)) == 1


# ============================================================================
# AC-002: Edit updates record, no duplicate
# ============================================================================


@pytest.mark.integration
async def test_edit_updates_not_duplicates(test_settings, ephemeral_pg, tmp_path: Path):
    """Re-indexing after editing a source document updates its record with no duplicate.

    The task's lessons section (body prose the parser carries into the payload)
    is edited between runs: the same record moves to version 2 with the new
    lessons, and only one record exists for the task.

    Acceptance criteria AC-002.
    """
    manifest = load_guardkit_manifest()
    task_id = unique_task_id("EDIT")
    corpus_root = tmp_path / "corpus"
    original_lessons = "Probe both venv locations before falling back."
    edited_lessons = "EDITED: fail loudly when neither venv location exists."
    task_path = write_task(corpus_root, task_id, lessons=original_lessons)

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        key = str(record_identity(natural_key_for(task_id)))

        # First run: original document published at version 1
        first_report = await reindex_corpus(
            corpus_root, manifest, direct_publisher, store=store
        )
        assert first_report.published_count == 1, first_report.to_json_dict()

        first_record = await store.aget(BUILD_OUTCOME_NAMESPACE, key)
        assert first_record is not None, "First run should create the record"
        assert first_record.value["version"] == 1
        assert stored_payload(first_record)["lessons"] == original_lessons

        # Edit the source document in place
        task_path.write_text(
            task_path.read_text(encoding="utf-8").replace(original_lessons, edited_lessons),
            encoding="utf-8",
        )

        # Second run over the edited corpus
        second_report = await reindex_corpus(
            corpus_root, manifest, direct_publisher, store=store
        )
        assert second_report.published_count == 1, second_report.to_json_dict()

        # Same record, next version, edited content
        second_record = await store.aget(BUILD_OUTCOME_NAMESPACE, key)
        assert second_record is not None
        assert second_record.value["version"] == first_record.value["version"] + 1
        assert second_record.value["content_hash"] != first_record.value["content_hash"]
        assert stored_payload(second_record)["lessons"] == edited_lessons

        # No duplicate: exactly one record carries this task's identifier
        matching_records = await records_for_identifier(store, task_id)
        assert [record.key for record in matching_records] == [key], (
            f"Expected 1 record for edited document, found {len(matching_records)}"
        )


# ============================================================================
# AC-003: Concurrent runs converge to single record
# ============================================================================


@pytest.mark.integration
async def test_concurrent_runs_converge(test_settings, ephemeral_pg, tmp_path: Path):
    """Two re-index runs started concurrently converge to exactly one record per key.

    Both runs walk the same five-task corpus at once, so their reads and writes
    interleave. Each run publishes every task, and the store ends with exactly
    one version-1 record per task.

    Acceptance criteria AC-003.
    """
    manifest = load_guardkit_manifest()
    corpus_root = tmp_path / "corpus"
    task_ids = [unique_task_id(f"CONC{index}") for index in range(5)]
    lessons_by_id = {}
    for index, task_id in enumerate(task_ids):
        lessons_by_id[task_id] = f"Concurrent lesson number {index}."
        write_task(corpus_root, task_id, lessons=lessons_by_id[task_id])

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        reports = await asyncio.gather(
            reindex_corpus(corpus_root, manifest, direct_publisher, store=store),
            reindex_corpus(corpus_root, manifest, direct_publisher, store=store),
        )

        expected_keys = sorted(natural_key_for(task_id) for task_id in task_ids)
        for report in reports:
            assert report.published_count == len(task_ids), report.to_json_dict()
            assert sorted(report.published_natural_keys) == expected_keys

        for task_id in task_ids:
            key = str(record_identity(natural_key_for(task_id)))
            matching_records = await records_for_identifier(store, task_id)
            assert [record.key for record in matching_records] == [key], (
                f"Concurrent runs should converge to 1 record for {task_id}, "
                f"found {len(matching_records)}"
            )

            record = matching_records[0]
            assert record.value["natural_key"] == natural_key_for(task_id)
            assert record.value["version"] == 1
            assert stored_payload(record)["lessons"] == lessons_by_id[task_id]


# ============================================================================
# AC-004: Double publish yields single record
# ============================================================================


@pytest.mark.integration
async def test_double_publish_single_record(test_settings, ephemeral_pg, make_adr_payload):
    """Publishing the same parsed document twice yields exactly one record for its natural key.

    Tests that writing the same payload twice via DeterministicWriter results in
    a single stored record with no duplicate.

    Acceptance criteria AC-004.
    """
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        # Create payload
        payload = make_adr_payload(
            identifier="ADR_DOUBLE_PUBLISH",
            decision="Test double publish idempotency",
        )

        # Write twice
        await writer.write(payload)
        await writer.write(payload)

        # Verify: exactly one record
        namespace = ("fleet_memory", "reindex_integration_test", "adr")
        key = str(record_identity(payload.natural_key))

        all_records = await store.asearch(namespace)
        matching_records = [r for r in all_records if r.key == key]

        assert (
            len(matching_records) == 1
        ), f"Double publish should yield 1 record, found {len(matching_records)}"

        # Verify record has version 1 (no version bump on duplicate publish)
        record = matching_records[0]
        assert record.value.get("version") == 1, "Duplicate publish should not increment version"
