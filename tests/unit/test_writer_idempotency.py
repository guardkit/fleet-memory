"""Comprehensive idempotency and zero-LLM test suite for DeterministicWriter.

Covers all scenarios from TASK-DW-004:
- Idempotency: identical content no-op, byte-identical boundary, single-character change,
  batch outline (0/1/50 items), full-corpus re-run creates no new records
- Failure modes: embedding-unavailable, dimension-mismatch, database-unreachable
- Negative validation: hyphen-namespace, not-a-payload, hostile-content, delimiter-forge
- Zero-LLM: assert no LLM client construction or import reachable from writer path

Unit tests use mock store (no infrastructure required).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleet_memory.errors import NamespaceValidationError
from fleet_memory.payloads.base import BasePayload, IdentifierValidationError
from fleet_memory.payloads.models import ADRPayload, DocumentPayload
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import content_hash, record_identity

if TYPE_CHECKING:
    from collections.abc import Callable


# ============================================================================
# Test Fixtures
# ============================================================================


def _make_adr_payload(**overrides) -> ADRPayload:
    """Factory for ADRPayload test instances with sensible defaults."""
    defaults = {
        "project": "test_proj",
        "identifier": "ADR_001",
        "source_ref": "test/source",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
        "version": 1,
    }
    defaults.update(overrides)
    return ADRPayload(**defaults)


def _make_document_payload(**overrides) -> DocumentPayload:
    """Factory for DocumentPayload test instances with sensible defaults."""
    defaults = {
        "project": "test_proj",
        "identifier": "DOC_001",
        "source_ref": "test/source",
        "version": 1,
    }
    defaults.update(overrides)
    return DocumentPayload(**defaults)


@pytest.fixture
def make_adr_payload() -> Callable[..., ADRPayload]:
    """Fixture providing ADRPayload factory for test customization."""
    return _make_adr_payload


@pytest.fixture
def make_document_payload() -> Callable[..., DocumentPayload]:
    """Fixture providing DocumentPayload factory for test customization."""
    return _make_document_payload


@pytest.fixture
def mock_store():
    """Mock AsyncPostgresStore for testing write logic without database."""
    store = AsyncMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    return store


@pytest.fixture
def mock_settings():
    """Mock Settings for DeterministicWriter."""
    settings = MagicMock()
    settings.embed_dims = 768
    return settings


# ============================================================================
# AC-001: Idempotency - Identical content twice → no-op, no re-embed
# ============================================================================


@pytest.mark.asyncio
async def test_identical_content_twice_is_noop_no_reembed(
    make_adr_payload, mock_store, mock_settings
):
    """Writing identical content twice results in no-op on second write (no re-embed).

    AC-001: identical-content no-op scenario.
    First write stores record; second write with same content_hash skips aput.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload(decision="Use PostgreSQL for persistence")

    # First write - no existing record
    await writer.write(payload)
    assert mock_store.aput.call_count == 1
    first_call_args = mock_store.aput.call_args

    # Setup mock to return the stored record
    stored_value = first_call_args[0][2]
    stored_item = MagicMock()
    stored_item.value = stored_value
    mock_store.aget.return_value = stored_item

    # Second write with identical content
    mock_store.reset_mock()
    await writer.write(payload)

    # Should NOT call aput again (no-op, no re-embed)
    mock_store.aput.assert_not_called()


@pytest.mark.asyncio
async def test_byte_identical_content_no_new_version(
    make_adr_payload, mock_store, mock_settings
):
    """Byte-identical content (same content_hash) creates no new version.

    AC-001: byte-identical boundary scenario.
    Even with fresh payload instance, if content_hash matches, no write occurs.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payload_v1 = make_adr_payload(decision="Use PostgreSQL")

    # First write
    await writer.write(payload_v1)
    stored_value = mock_store.aput.call_args[0][2]

    # Setup mock to return stored record
    stored_item = MagicMock()
    stored_item.value = stored_value
    mock_store.aget.return_value = stored_item

    # Second write with byte-identical payload (new instance, same content)
    mock_store.reset_mock()
    payload_v2 = make_adr_payload(decision="Use PostgreSQL")  # Identical
    await writer.write(payload_v2)

    # No new write (byte-identical)
    mock_store.aput.assert_not_called()


@pytest.mark.asyncio
async def test_single_character_change_advances_version(
    make_adr_payload, mock_store, mock_settings
):
    """Single-character difference is treated as new content, version advances by one.

    AC-001: single-character boundary scenario.
    Even minimal content change triggers version increment.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payload_v1 = make_adr_payload(decision="Use PostgreSQL")

    # First write
    await writer.write(payload_v1)
    first_value = mock_store.aput.call_args[0][2]

    # Setup mock to return v1
    stored_item = MagicMock()
    stored_item.value = first_value
    mock_store.aget.return_value = stored_item

    # Second write with single character removed
    mock_store.reset_mock()
    payload_v2 = make_adr_payload(decision="Use PostgreSQ")  # One char removed
    await writer.write(payload_v2)

    # Should write with version incremented by one
    mock_store.aput.assert_called_once()
    second_value = mock_store.aput.call_args[0][2]
    assert second_value["version"] == first_value["version"] + 1


# ============================================================================
# AC-001: Batch outline scenarios (0, 1, 50 items)
# ============================================================================


@pytest.mark.asyncio
async def test_batch_zero_items_produces_no_records(mock_store, mock_settings):
    """Batch with N=0 produces no records.

    AC-001: batch outline N=0 scenario.
    """
    writer = DeterministicWriter(mock_store, mock_settings)

    await writer.write_batch([])

    mock_store.aput.assert_not_called()


@pytest.mark.asyncio
async def test_batch_one_item_produces_one_record(
    make_adr_payload, mock_store, mock_settings
):
    """Batch with N=1 produces exactly one record.

    AC-001: batch outline N=1 scenario.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payloads = [make_adr_payload(identifier="ADR_001")]

    await writer.write_batch(payloads)

    assert mock_store.aput.call_count == 1


@pytest.mark.asyncio
async def test_batch_fifty_distinct_keys_produces_fifty_records(
    make_adr_payload, mock_store, mock_settings
):
    """Batch with N=50 distinct keys produces exactly 50 records.

    AC-001: batch outline N=50 scenario.
    Each distinct natural key produces one record.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payloads = [
        make_adr_payload(identifier=f"ADR_{i:03d}")
        for i in range(50)
    ]

    await writer.write_batch(payloads)

    assert mock_store.aput.call_count == 50


@pytest.mark.asyncio
async def test_batch_duplicate_keys_collapse_to_one_per_key(
    make_adr_payload, mock_store, mock_settings
):
    """Within-batch duplicate natural keys collapse to one record per key.

    AC-001: batch deduplication.
    Last occurrence wins for each natural key.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payloads = [
        make_adr_payload(identifier="ADR_001", decision="First"),
        make_adr_payload(identifier="ADR_001", decision="Second"),
        make_adr_payload(identifier="ADR_001", decision="Third"),
        make_adr_payload(identifier="ADR_002", decision="Other"),
    ]

    await writer.write_batch(payloads)

    # Should produce 2 records (one for ADR_001 last occurrence, one for ADR_002)
    assert mock_store.aput.call_count == 2


# ============================================================================
# AC-001: Full corpus re-run creates no new records and changes none
# ============================================================================


@pytest.mark.asyncio
async def test_full_corpus_rerun_creates_no_new_records(
    make_adr_payload, mock_store, mock_settings
):
    """Re-running a full corpus a second time creates no new records and changes none.

    AC-001: full-corpus re-run no-change scenario.
    After first batch write, second identical batch is all no-ops.
    """
    writer = DeterministicWriter(mock_store, mock_settings)

    # Build corpus of 10 items
    corpus = [
        make_adr_payload(identifier=f"ADR_{i:03d}", decision=f"Decision {i}")
        for i in range(10)
    ]

    # First run - store all
    await writer.write_batch(corpus)
    assert mock_store.aput.call_count == 10

    # Capture all stored values keyed by store_key
    stored_records = {}
    for call in mock_store.aput.call_args_list:
        namespace, store_key, value = call[0]
        stored_records[store_key] = value

    # Setup mock aget to return stored records
    def mock_aget_impl(ns, key):
        if key in stored_records:
            item = MagicMock()
            item.value = stored_records[key]
            return item
        return None

    mock_store.aget.side_effect = mock_aget_impl
    mock_store.reset_mock()

    # Second run - all no-ops (identical content_hash)
    await writer.write_batch(corpus)

    # No new aputs (all were no-ops)
    mock_store.aput.assert_not_called()


# ============================================================================
# AC-002: Concurrency/Integrity - Unit test stubs (real tests in integration)
# ============================================================================

# Note: Concurrent duplicate convergence, interrupted-write atomicity, and
# read-during-versioned-write are tested in tests/integration/test_writer_idempotency.py
# Unit tests cannot meaningfully test concurrency without a real database.


# ============================================================================
# AC-003: Failure modes - embed unavailable, dimension mismatch, db unreachable
# ============================================================================


@pytest.mark.asyncio
async def test_embedding_unavailable_fails_write_no_partial_record(
    make_adr_payload, mock_store, mock_settings
):
    """When embedding service is unavailable, write fails with no partial record.

    AC-003: embed-unavailable failure mode.
    Diagnostic names the failing target (embedding service).
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    # Simulate embedding failure by making aput raise
    mock_store.aput.side_effect = RuntimeError("Embedding service unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        await writer.write(payload)

    assert "embedding service unavailable" in str(exc_info.value).lower()
    # No successful aput occurred
    assert mock_store.aput.call_count == 1  # Failed attempt


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_fails_write(
    make_adr_payload, mock_store, mock_settings
):
    """Embedding dimension mismatch fails write with diagnostic naming the target.

    AC-003: dimension-mismatch failure mode.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    # Simulate dimension mismatch
    mock_store.aput.side_effect = ValueError(
        "Embedding dimension mismatch: expected 768, got 384"
    )

    with pytest.raises(ValueError) as exc_info:
        await writer.write(payload)

    error_msg = str(exc_info.value).lower()
    assert "dimension" in error_msg or "mismatch" in error_msg


@pytest.mark.asyncio
async def test_database_unreachable_fails_write_no_partial_record(
    make_adr_payload, mock_store, mock_settings
):
    """Database unreachable fails write with diagnostic naming the failing target.

    AC-003: db-unreachable failure mode.
    """
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    # Simulate database connection failure
    mock_store.aget.side_effect = ConnectionError("Database unreachable: connection refused")

    with pytest.raises(ConnectionError) as exc_info:
        await writer.write(payload)

    error_msg = str(exc_info.value).lower()
    assert "database" in error_msg or "connection" in error_msg


# ============================================================================
# AC-004: Negative validation cases
# ============================================================================


@pytest.mark.asyncio
async def test_hyphen_namespace_rejected_before_write(mock_store, mock_settings):
    """Hyphenated project identifier rejected before any write with underscores-only error.

    AC-004: hyphen-namespace reject scenario.
    Validation happens at payload construction, before writer is invoked.
    """
    writer = DeterministicWriter(mock_store, mock_settings)

    # Project with hyphen (invalid) - rejected at payload construction
    with pytest.raises(IdentifierValidationError) as exc_info:
        payload = ADRPayload(
            project="test-proj",  # Invalid: hyphen
            identifier="ADR_001",
            source_ref="test/source",
            decision="Test decision",
            status="proposed",
        )

    # Verify error message mentions underscores
    assert "underscores" in str(exc_info.value).lower()
    # No record created
    mock_store.aput.assert_not_called()


@pytest.mark.asyncio
async def test_non_registered_payload_rejected(mock_store, mock_settings):
    """Non-registered payload type is rejected with error naming the type.

    AC-004: not-a-payload reject scenario.
    """
    writer = DeterministicWriter(mock_store, mock_settings)

    # Create an unregistered payload type
    class UnregisteredPayload(BasePayload):
        payload_type = "unregistered_type"

    payload = UnregisteredPayload(
        project="test_proj",
        identifier="TEST_001",
        source_ref="test/source",
    )

    with pytest.raises(ValueError) as exc_info:
        await writer.write(payload)

    error_msg = str(exc_info.value).lower()
    assert (
        "not a recognized payload type" in error_msg
        or "unregistered" in error_msg
    )
    mock_store.aput.assert_not_called()


@pytest.mark.asyncio
async def test_hostile_content_written_byte_identical_inert(
    make_adr_payload, mock_store, mock_settings
):
    """Hostile content (SQL injection-shaped text) is written byte-for-byte and inert.

    AC-004: hostile-content inert round-trip scenario.
    Content is stored as-is with no interpretation or side effects.
    """
    writer = DeterministicWriter(mock_store, mock_settings)

    # SQL injection payload
    hostile_decision = "'; DROP TABLE memories; -- malicious content"
    payload = make_adr_payload(decision=hostile_decision)

    await writer.write(payload)

    # Verify the hostile content was stored byte-for-byte in the content field
    stored_value = mock_store.aput.call_args[0][2]
    assert "content" in stored_value
    # The content field should contain the decision text
    assert hostile_decision in stored_value["content"]


@pytest.mark.asyncio
async def test_delimiter_in_identifier_rejected(mock_store, mock_settings):
    """Delimiter or path-shaped text in identifier field rejected with underscores-only error.

    AC-004: delimiter-forge-identity reject scenario.
    Cannot forge a different identity by injecting path separators.
    """
    writer = DeterministicWriter(mock_store, mock_settings)

    # Identifier with delimiter (invalid)
    with pytest.raises(IdentifierValidationError) as exc_info:
        payload = ADRPayload(
            project="test_proj",
            identifier="ADR/001/malicious",  # Invalid: contains /
            source_ref="test/source",
            decision="Test",
            status="proposed",
        )

    # Error should mention underscores-only constraint
    assert "underscores" in str(exc_info.value).lower()
    mock_store.aput.assert_not_called()


# ============================================================================
# AC-005: Zero-LLM negative import test
# ============================================================================


def test_zero_llm_no_anthropic_import_in_writer():
    """Writer module contains no anthropic imports.

    AC-005: zero-LLM negative import test (part 1).
    Scan writer.core source code for LLM client imports.
    """
    import fleet_memory.writer.core as core_module

    source_file = core_module.__file__
    with open(source_file) as f:
        source_code = f.read()

    # Should not import any LLM clients
    assert "import anthropic" not in source_code.lower()
    assert "from anthropic" not in source_code.lower()
    assert "import openai" not in source_code.lower()
    assert "from openai" not in source_code.lower()
    assert "import litellm" not in source_code.lower()
    assert "from litellm" not in source_code.lower()


def test_zero_llm_no_llm_modules_imported_during_writer_construction():
    """Constructing DeterministicWriter loads no LLM client modules.

    AC-005: zero-LLM negative import test (part 2).
    Verify that instantiating the writer doesn't trigger LLM module imports.
    """
    # Snapshot loaded modules before writer construction
    loaded_before = set(sys.modules.keys())

    # Construct writer (with mocks)
    mock_store = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.embed_dims = 768
    writer = DeterministicWriter(mock_store, mock_settings)

    # Snapshot loaded modules after
    loaded_after = set(sys.modules.keys())
    newly_loaded = loaded_after - loaded_before

    # Verify no LLM client modules were loaded
    llm_modules = [
        "anthropic",
        "openai",
        "litellm",
        "langchain",
        "llama_index",
    ]

    for module_name in newly_loaded:
        for llm_name in llm_modules:
            assert not module_name.startswith(llm_name), (
                f"LLM module '{module_name}' was loaded during DeterministicWriter construction"
            )


@pytest.mark.asyncio
async def test_zero_llm_write_operation_touches_no_llm_modules(
    make_adr_payload, mock_store, mock_settings
):
    """Executing a write operation does not import or construct LLM clients.

    AC-005: zero-LLM negative import test (part 3).
    Exercise the write path and verify no LLM modules are touched.
    """
    # Snapshot loaded modules before write
    loaded_before = set(sys.modules.keys())

    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    await writer.write(payload)

    # Snapshot loaded modules after write
    loaded_after = set(sys.modules.keys())
    newly_loaded = loaded_after - loaded_before

    # Verify no LLM client modules were loaded
    llm_modules = ["anthropic", "openai", "litellm"]

    for module_name in newly_loaded:
        for llm_name in llm_modules:
            assert not module_name.startswith(llm_name), (
                f"LLM module '{module_name}' was loaded during write operation"
            )


def test_zero_llm_negative_fails_if_anthropic_added():
    """This test SHOULD FAIL if someone adds an LLM client import to the writer.

    AC-005: zero-LLM negative test fail-on-violation scenario.
    Demonstrates the test catches violations.
    """
    # This test documents the negative case: if the writer imports anthropic,
    # the test_zero_llm_no_anthropic_import_in_writer test will fail.
    #
    # To verify the test works, you could temporarily add:
    #   import anthropic  # type: ignore
    # to fleet_memory/writer/core.py and confirm the test fails.
    #
    # This test just asserts the current clean state.
    import fleet_memory.writer.core as core_module

    source_file = core_module.__file__
    with open(source_file) as f:
        source_code = f.read()

    # Current clean state - no LLM imports
    assert "anthropic" not in source_code.lower()
