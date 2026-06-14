"""Integration tests for re-index idempotency, concurrency, and convergence.

Marker-gated (@pytest.mark.integration) tests validating the
writer → store path against ephemeral PostgreSQL + pgvector (hermetic,
no NATS dependency):

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
from fleet_memory.payloads.models import ADRPayload, SeedModulePayload
from fleet_memory.reindex.pipeline import reindex_corpus
from fleet_memory.store import async_store_context
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import record_identity

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


def _make_seed_module_payload(**overrides) -> SeedModulePayload:
    """Factory for SeedModulePayload test instances with sensible defaults."""
    defaults = {
        "project": "reindex_integration_test",
        "identifier": "core_auth",
        "source_ref": "integration/reindex/seed/core_auth.md",
        "module_path": "src/auth.py",
        "version": 1,
    }
    defaults.update(overrides)
    return SeedModulePayload(**defaults)


@pytest.fixture
def make_adr_payload() -> Callable[..., ADRPayload]:
    """Fixture providing ADRPayload factory for integration tests."""
    return _make_adr_payload


@pytest.fixture
def make_seed_module_payload() -> Callable[..., SeedModulePayload]:
    """Fixture providing SeedModulePayload factory for integration tests."""
    return _make_seed_module_payload


def _create_test_corpus(tmp_path: Path, documents: dict[str, str]) -> Path:
    """Create a test corpus directory with the given documents.

    Args:
        tmp_path: Temporary directory for the corpus
        documents: Mapping of relative path to content

    Returns:
        Path to the corpus root
    """
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir(exist_ok=True)

    for rel_path, content in documents.items():
        doc_path = corpus_root / rel_path
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(content, encoding="utf-8")

    return corpus_root


# ============================================================================
# AC-001: Second run over unchanged corpus is no-op
# ============================================================================


@pytest.mark.integration
async def test_second_run_is_noop(test_settings, ephemeral_pg):
    """Second run over an unchanged corpus creates or modifies no stored record.

    Tests the writer → store path to ensure idempotency at the database level:
    running reindex_corpus twice on the same unchanged corpus results in only
    one record per document with no version increment.

    Acceptance criteria AC-001.
    """
    # Setup: ephemeral store with fake embeddings
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        # Create publisher that writes directly via DeterministicWriter
        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        # Create test corpus
        tmp_path = Path("/tmp/test_reindex_noop")
        tmp_path.mkdir(exist_ok=True)
        documents = {
            "adr/ADR_001.md": """---
type: adr
project: reindex_integration_test
identifier: ADR_001
decision: Use PostgreSQL for persistence
status: accepted
---
# ADR 001
"""
        }
        corpus_root = _create_test_corpus(tmp_path, documents)

        # First run: publish corpus
        await reindex_corpus(corpus_root, publisher=direct_publisher)

        # Read first version
        namespace = ("fleet_memory", "reindex_integration_test", "adr")
        key = str(record_identity("adr:reindex_integration_test:ADR_001"))
        first_record = await store.aget(namespace, key)
        assert first_record is not None, "First run should create record"
        first_version = first_record.value.get("version", 1)

        # Second run: publish same corpus
        await reindex_corpus(corpus_root, publisher=direct_publisher)

        # Read second version
        second_record = await store.aget(namespace, key)
        assert second_record is not None
        second_version = second_record.value.get("version", 1)

        # Assert: version unchanged (no-op on second run)
        assert (
            second_version == first_version
        ), f"Second run should be no-op, but version changed: {first_version} → {second_version}"


# ============================================================================
# AC-002: Edit updates record, no duplicate
# ============================================================================


@pytest.mark.integration
async def test_edit_updates_not_duplicates(test_settings, ephemeral_pg):
    """Re-indexing after editing a source document updates its record with no duplicate.

    Tests that editing a document and re-running reindex_corpus results in a
    version++ update to the existing record, not a new duplicate record.

    Acceptance criteria AC-002.
    """
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        # Create test corpus with initial content
        tmp_path = Path("/tmp/test_reindex_edit")
        tmp_path.mkdir(exist_ok=True)
        documents_v1 = {
            "seed/core_auth.md": """---
type: seed_module
project: reindex_integration_test
identifier: core_auth
module_path: src/auth.py
---
# Initial content
"""
        }
        corpus_root = _create_test_corpus(tmp_path, documents_v1)

        # First run
        await reindex_corpus(corpus_root, publisher=direct_publisher)

        namespace = ("fleet_memory", "reindex_integration_test", "seed_module")
        key = str(record_identity("seed_module:reindex_integration_test:core_auth"))
        first_record = await store.aget(namespace, key)
        assert first_record is not None
        first_version = first_record.value.get("version", 1)

        # Edit the document (change module_path to trigger content hash change)
        edited_path = corpus_root / "seed/core_auth.md"
        edited_path.write_text(
            """---
type: seed_module
project: reindex_integration_test
identifier: core_auth
module_path: src/auth_v2.py
---
# EDITED content with new module path
""",
            encoding="utf-8",
        )

        # Second run with edited content
        await reindex_corpus(corpus_root, publisher=direct_publisher)

        # Verify: single record with version increment
        second_record = await store.aget(namespace, key)
        assert second_record is not None
        second_version = second_record.value.get("version", 1)

        # Assert version incremented
        assert (
            second_version == first_version + 1
        ), f"Edit should increment version: {first_version} → {second_version}"

        # Assert: only one record exists (no duplicate)
        # Search entire namespace for this identifier
        all_records = await store.asearch(namespace)
        matching_records = [r for r in all_records if r.key == key]
        assert (
            len(matching_records) == 1
        ), f"Expected 1 record for edited document, found {len(matching_records)}"


# ============================================================================
# AC-003: Concurrent runs converge to single record
# ============================================================================


@pytest.mark.integration
async def test_concurrent_runs_converge(test_settings, ephemeral_pg):
    """Two re-index runs started concurrently converge to exactly one record per key.

    Tests that overlapping concurrent reindex_corpus runs on the same corpus
    converge to a single stored record per natural key, with no duplicates.

    Acceptance criteria AC-003.
    """
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        # Create test corpus
        tmp_path = Path("/tmp/test_reindex_concurrent")
        tmp_path.mkdir(exist_ok=True)
        documents = {
            "adr/ADR_CONCURRENT.md": """---
type: adr
project: reindex_integration_test
identifier: ADR_CONCURRENT
decision: Test concurrent writes
status: accepted
---
# Concurrent test
"""
        }
        corpus_root = _create_test_corpus(tmp_path, documents)

        # Run two reindex_corpus calls concurrently
        await asyncio.gather(
            reindex_corpus(corpus_root, publisher=direct_publisher),
            reindex_corpus(corpus_root, publisher=direct_publisher),
        )

        # Verify: exactly one record exists
        namespace = ("fleet_memory", "reindex_integration_test", "adr")
        key = str(record_identity("adr:reindex_integration_test:ADR_CONCURRENT"))

        all_records = await store.asearch(namespace)
        matching_records = [r for r in all_records if r.key == key]

        assert (
            len(matching_records) == 1
        ), f"Concurrent runs should converge to 1 record, found {len(matching_records)}"

        # Verify record is valid
        record = matching_records[0]
        assert record.value.get("identifier") == "ADR_CONCURRENT"


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
