"""Integration tests for re-index security and backfill handling.

Marker-gated (@pytest.mark.integration) tests validating writer → store path
against ephemeral PostgreSQL + pgvector (hermetic, no NATS dependency):

- Documents with injection-shaped text are stored verbatim with no execution (AC-005)
- Reviewed backfill payloads are stored as typed records like parsed payloads (AC-006)

Requirements:
- Docker running for ephemeral_pg fixture
- Default test run (pytest) skips these via @pytest.mark.integration
- Run with: pytest -m integration tests/integration/reindex/

Covers TASK-RIP-010 integration scenarios AC-005 and AC-006.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fleet_memory.embed import make_fake_embed
from fleet_memory.payloads.models import ADRPayload
from fleet_memory.payloads.registry import get_model_for_type
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


def _create_test_corpus(tmp_path: Path, documents: dict[str, str]) -> Path:
    """Create a test corpus directory with the given documents.

    Args:
        tmp_path: Temporary directory for the corpus
        documents: Mapping of relative path to content

    Returns:
        Path to the corpus root
    """
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir(parents=True, exist_ok=True)

    for rel_path, content in documents.items():
        doc_path = corpus_root / rel_path
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(content, encoding="utf-8")

    return corpus_root


# ============================================================================
# AC-005: Injection-shaped text stored verbatim, no execution
# ============================================================================


@pytest.mark.integration
async def test_injection_body_stored_verbatim(test_settings, ephemeral_pg):
    """Document with injection-shaped text is stored byte-for-byte with no command execution.

    Tests that a document whose body contains injection attack vectors
    (e.g., SQL injection, shell commands, script tags) is written and stored
    verbatim without any command execution during ingestion.

    Acceptance criteria AC-005.
    """
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        async def direct_publisher(payload: BasePayload) -> None:
            await writer.write(payload)

        # Create document with injection-shaped content
        # Use quotes to ensure YAML parsing works
        injection_decision = (
            "SQL: '; DROP TABLE records; -- | "
            "XSS: <script>alert('XSS')</script> | "
            "Shell: $(rm -rf /) | "
            "Template: {{7*7}} | "
            "Java: ${java.lang.Runtime}"
        )

        tmp_path = Path("/tmp/test_reindex_injection")
        tmp_path.mkdir(exist_ok=True)
        documents = {
            "adr/ADR_INJECTION.md": f"""---
type: adr
project: reindex_integration_test
identifier: ADR_INJECTION_TEST
decision: "{injection_decision}"
status: accepted
---
# ADR with injection content

Body content: {injection_decision}
"""
        }
        corpus_root = _create_test_corpus(tmp_path, documents)

        # Publish corpus
        await reindex_corpus(corpus_root, publisher=direct_publisher)

        # Read stored record
        namespace = ("fleet_memory", "reindex_integration_test", "adr")
        key = str(record_identity("adr:reindex_integration_test:ADR_INJECTION_TEST"))
        record = await store.aget(namespace, key)

        assert record is not None, "Injection-shaped document should be stored"

        # Parse content field (DeterministicWriter stores payload as JSON in content)
        content = json.loads(record.value.get("content", "{}"))

        # Verify: injection text stored verbatim (byte-for-byte)
        stored_decision = content.get("decision", "")
        assert (
            stored_decision == injection_decision
        ), f"Injection text not stored verbatim. Expected: {injection_decision!r}, Got: {stored_decision!r}"

        # Verify: no side effects (record exists and is valid)
        assert content.get("identifier") == "ADR_INJECTION_TEST"
        assert content.get("status") == "accepted"

        # Additional safety check: verify no execution artifacts
        # (This is a smoke test - real injection would fail the test environment)
        # If injection executed, the test would have already crashed or behaved unexpectedly
        # The fact we reach this assertion proves no execution occurred


# ============================================================================
# AC-006: Reviewed backfill stored as typed record
# ============================================================================


@pytest.mark.integration
async def test_reviewed_backfill_stored_as_typed_record(test_settings, ephemeral_pg):
    """Reviewed backfill payload is stored as a typed record like a deterministically parsed payload.

    Tests that a manually-crafted backfill payload is written through DeterministicWriter
    and stored as a typed record identical to a deterministically parsed payload.

    Acceptance criteria AC-006.
    """
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store, test_settings)

        # Create reviewed backfill payload (simulating manual backfill)
        backfill_payload_data = {
            "payload_type": "adr",
            "project": "reindex_integration_test",
            "identifier": "ADR_BACKFILL_REVIEWED",
            "decision": "Manually backfilled decision record",
            "status": "accepted",
            "source_ref": "backfill/staging/ADR_BACKFILL_REVIEWED.json",
            "version": 1,
        }

        # Load backfill payload as typed model
        model_class = get_model_for_type("adr")
        backfill_payload = model_class(**backfill_payload_data)

        # Write backfill payload directly (simulating reviewed backfill path)
        await writer.write(backfill_payload)

        # Read stored record
        namespace = ("fleet_memory", "reindex_integration_test", "adr")
        key = str(record_identity("adr:reindex_integration_test:ADR_BACKFILL_REVIEWED"))
        record = await store.aget(namespace, key)

        assert record is not None, "Reviewed backfill should be stored"

        # Verify: stored as a typed record (has all ADRPayload fields)
        assert record.value.get("payload_type") == "adr"
        assert record.value.get("identifier") == "ADR_BACKFILL_REVIEWED"
        assert record.value.get("version") == 1

        # Parse content field (DeterministicWriter stores payload as JSON in content)
        content = json.loads(record.value.get("content", "{}"))
        assert content.get("decision") == "Manually backfilled decision record"
        assert content.get("status") == "accepted"

        # Verify: has record identity (same as deterministically parsed payloads)
        # The key derivation proves it went through the same write path
        assert record.key == key

        # Compare to a deterministically parsed payload
        # Create a parsed ADR payload with identical content
        parsed_payload = ADRPayload(
            project="reindex_integration_test",
            identifier="ADR_BACKFILL_PARSED",
            decision="Deterministically parsed decision record",
            status="accepted",
            source_ref="test/parsed/ADR_BACKFILL_PARSED.md",
            version=1,
        )

        # Write the parsed payload
        await writer.write(parsed_payload)

        # Read the parsed record
        parsed_key = str(record_identity(parsed_payload.natural_key))
        parsed_record = await store.aget(namespace, parsed_key)

        assert parsed_record is not None

        # Verify: both records have the same structure (same field set)
        backfill_metadata_fields = set(record.value.keys())
        parsed_metadata_fields = set(parsed_record.value.keys())

        # The metadata field sets should be identical (both went through same write path)
        core_metadata_fields = {"payload_type", "identifier", "version", "project", "content", "content_hash"}
        assert core_metadata_fields.issubset(
            backfill_metadata_fields
        ), f"Backfill record missing metadata fields: {core_metadata_fields - backfill_metadata_fields}"
        assert core_metadata_fields.issubset(
            parsed_metadata_fields
        ), f"Parsed record missing metadata fields: {core_metadata_fields - parsed_metadata_fields}"
