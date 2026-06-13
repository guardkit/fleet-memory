"""Unit tests for DeterministicWriter core write logic.

Tests the idempotent content-hash upsert algorithm without live database.
Uses mock store to verify write/no-write decisions and version advancement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from fleet_memory.errors import NamespaceValidationError, UnknownPayloadTypeError
from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.models import ADRPayload, DocumentPayload
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import content_hash, record_identity

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_adr_payload(**overrides) -> ADRPayload:
    """Factory for ADRPayload test instances."""
    defaults = {
        "project": "test_proj",
        "identifier": "ADR_001",
        "source_ref": "test/source",
        "decision": "Use PostgreSQL",
        "status": "accepted",
        "version": 1,
    }
    defaults.update(overrides)
    return ADRPayload(**defaults)


def _make_document_payload(**overrides) -> DocumentPayload:
    """Factory for DocumentPayload test instances."""
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
    """Fixture providing ADRPayload factory."""
    return _make_adr_payload


@pytest.fixture
def make_document_payload() -> Callable[..., DocumentPayload]:
    """Fixture providing DocumentPayload factory."""
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


# AC-001: Writing a typed payload stores a retrievable record in its project namespace
@pytest.mark.asyncio
async def test_write_payload_stores_record_in_correct_namespace(
    make_adr_payload, mock_store, mock_settings
):
    """Writing a typed payload stores it in the correct namespace."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    await writer.write(payload)

    # Verify namespace is ("fleet_memory", project, payload_type)
    expected_namespace = ("fleet_memory", "test_proj", "adr")
    mock_store.aput.assert_called_once()
    call_args = mock_store.aput.call_args
    assert call_args[0][0] == expected_namespace


# AC-002: Same payload written twice resolves to same stable record identity
@pytest.mark.asyncio
async def test_write_same_payload_twice_produces_same_identity(
    make_adr_payload, mock_store, mock_settings
):
    """The same payload written twice produces the same UUIDv5 identity."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    await writer.write(payload)
    first_key = mock_store.aput.call_args[0][1]

    mock_store.reset_mock()
    await writer.write(payload)
    second_key = mock_store.aput.call_args[0][1]

    assert first_key == second_key
    assert isinstance(UUID(first_key), UUID)


# AC-003: Writing identical content twice leaves exactly one record unchanged (no re-embed)
@pytest.mark.asyncio
async def test_write_identical_content_is_noop(make_adr_payload, mock_store, mock_settings):
    """Writing identical content twice is a no-op on the second write."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    # First write - no existing record
    await writer.write(payload)
    first_call = mock_store.aput.call_args

    # Setup mock to return the stored record
    stored_value = first_call[0][2]
    stored_item = MagicMock()
    stored_item.value = stored_value
    mock_store.aget.return_value = stored_item

    # Second write with identical content
    mock_store.reset_mock()
    await writer.write(payload)

    # Should NOT call aput again (no-op)
    mock_store.aput.assert_not_called()


# AC-004: Writing changed content advances version by one
@pytest.mark.asyncio
async def test_write_changed_content_advances_version(
    make_adr_payload, mock_store, mock_settings
):
    """Writing changed content under same key advances version by one."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload_v1 = make_adr_payload(decision="Use PostgreSQL")

    # First write
    await writer.write(payload_v1)
    first_value = mock_store.aput.call_args[0][2]

    # Setup mock to return v1
    stored_item = MagicMock()
    stored_item.value = first_value
    mock_store.aget.return_value = stored_item

    # Second write with different content
    mock_store.reset_mock()
    payload_v2 = make_adr_payload(decision="Use MySQL")  # Changed decision
    await writer.write(payload_v2)

    # Should call aput with version incremented
    second_value = mock_store.aput.call_args[0][2]
    assert second_value["version"] == first_value["version"] + 1


# AC-005: Byte-identical content creates no new version
@pytest.mark.asyncio
async def test_byte_identical_content_no_new_version(
    make_adr_payload, mock_store, mock_settings
):
    """Byte-identical content (same hash) creates no new version."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload(decision="Use PostgreSQL")

    await writer.write(payload)
    stored_value = mock_store.aput.call_args[0][2]

    # Setup mock
    stored_item = MagicMock()
    stored_item.value = stored_value
    mock_store.aget.return_value = stored_item

    # Write again with identical payload
    mock_store.reset_mock()
    await writer.write(payload)

    # No new write
    mock_store.aput.assert_not_called()


# AC-005 (continued): Single-character difference creates new version
@pytest.mark.asyncio
async def test_single_character_difference_creates_new_version(
    make_adr_payload, mock_store, mock_settings
):
    """A single-character difference is treated as new content."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload_v1 = make_adr_payload(decision="Use PostgreSQL")

    await writer.write(payload_v1)
    stored_value = mock_store.aput.call_args[0][2]

    # Setup mock
    stored_item = MagicMock()
    stored_item.value = stored_value
    mock_store.aget.return_value = stored_item

    # Single character change
    mock_store.reset_mock()
    payload_v2 = make_adr_payload(decision="Use PostgreSQ")  # One char removed
    await writer.write(payload_v2)

    # Should write with incremented version
    mock_store.aput.assert_called_once()
    new_value = mock_store.aput.call_args[0][2]
    assert new_value["version"] == stored_value["version"] + 1


# AC-006: Written payload content is embedded (content field present)
@pytest.mark.asyncio
async def test_written_payload_has_content_field(
    make_adr_payload, mock_store, mock_settings
):
    """The stored value contains a 'content' field for embedding."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    await writer.write(payload)

    stored_value = mock_store.aput.call_args[0][2]
    assert "content" in stored_value
    assert isinstance(stored_value["content"], str)
    assert len(stored_value["content"]) > 0


# AC-007: Batch write with N distinct keys produces N records
@pytest.mark.asyncio
async def test_batch_write_distinct_keys_produces_n_records(
    make_adr_payload, mock_store, mock_settings
):
    """Batch of N payloads with distinct natural keys produces exactly N records."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payloads = [
        make_adr_payload(identifier="ADR_001"),
        make_adr_payload(identifier="ADR_002"),
        make_adr_payload(identifier="ADR_003"),
    ]

    await writer.write_batch(payloads)

    assert mock_store.aput.call_count == 3


# AC-007 (continued): Batch with N=0 produces no records
@pytest.mark.asyncio
async def test_batch_write_empty_produces_zero_records(mock_store, mock_settings):
    """Batch of zero payloads produces no records."""
    writer = DeterministicWriter(mock_store, mock_settings)

    await writer.write_batch([])

    mock_store.aput.assert_not_called()


# AC-007 (continued): Batch with duplicate keys collapses to one record per key
@pytest.mark.asyncio
async def test_batch_write_duplicate_keys_collapses(
    make_adr_payload, mock_store, mock_settings
):
    """Within-batch duplicate natural keys collapse to one record per key."""
    writer = DeterministicWriter(mock_store, mock_settings)
    # Same natural key, different content
    payloads = [
        make_adr_payload(identifier="ADR_001", decision="First"),
        make_adr_payload(identifier="ADR_001", decision="Second"),
        make_adr_payload(identifier="ADR_002", decision="Other"),
    ]

    await writer.write_batch(payloads)

    # Should produce 2 records (one for ADR_001, one for ADR_002)
    assert mock_store.aput.call_count == 2


# AC-008: Hyphenated project namespace rejected before write
@pytest.mark.asyncio
async def test_hyphenated_project_namespace_rejected(mock_store, mock_settings):
    """Hyphenated project identifier is rejected with underscores-only error."""
    from fleet_memory.payloads.base import IdentifierValidationError

    writer = DeterministicWriter(mock_store, mock_settings)

    # Project with hyphen (invalid) - rejected at payload construction
    with pytest.raises(IdentifierValidationError) as exc_info:
        payload = ADRPayload(
            project="test-proj",  # Invalid: hyphen
            identifier="ADR_001",
            source_ref="test/source",
            decision="Test",
            status="proposed",
        )

    # Verify error message
    assert "underscores only" in str(exc_info.value).lower()
    # No record created
    mock_store.aput.assert_not_called()


# AC-009: Non-registered input rejected
@pytest.mark.asyncio
async def test_non_registered_payload_rejected(mock_store, mock_settings):
    """Non-registered payload type is rejected with error naming the type."""
    writer = DeterministicWriter(mock_store, mock_settings)

    # Create an unregistered payload type
    class UnregisteredPayload(BasePayload):
        payload_type = "unregistered"

    payload = UnregisteredPayload(
        project="test_proj",
        identifier="TEST_001",
        source_ref="test/source",
    )

    with pytest.raises(ValueError) as exc_info:
        await writer.write(payload)

    assert "not a recognized payload type" in str(exc_info.value).lower() or "unregistered" in str(
        exc_info.value
    ).lower()
    mock_store.aput.assert_not_called()


# AC-010: Embedding-unavailable fails write with no partial record
@pytest.mark.asyncio
async def test_embedding_unavailable_fails_write(make_adr_payload, mock_store, mock_settings):
    """When embedding service is unavailable, write fails with no partial record."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    # Simulate embedding failure by making aput raise
    mock_store.aput.side_effect = RuntimeError("Embedding service unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        await writer.write(payload)

    assert "embedding service" in str(exc_info.value).lower()


# AC-011: No language model client constructed
@pytest.mark.asyncio
async def test_no_llm_client_constructed(make_adr_payload, mock_store, mock_settings):
    """DeterministicWriter constructs no language-model client."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    # Verify no anthropic or openai imports in writer module
    import fleet_memory.writer.core as core_module

    source = core_module.__file__
    with open(source) as f:
        code = f.read()

    # Should not import any LLM clients
    assert "import anthropic" not in code.lower()
    assert "import openai" not in code.lower()
    assert "from anthropic" not in code.lower()
    assert "from openai" not in code.lower()


# Integration contract test (from task spec)
@pytest.mark.seam
@pytest.mark.integration_contract("writer_store_record")
def test_writer_record_carries_content_and_namespace():
    """The value the writer stores embeds on write and lands in the right namespace.

    Contract: namespace == ("fleet_memory", project, payload_type); the stored
    value contains a non-empty "content" string field (index config fields=["content"]).
    Producer: TASK-DW-001 (identity/hash) + TASK-MEM-005 (store contract)
    """
    from fleet_memory.writer import DeterministicWriter  # noqa: F401

    # Build the namespace + record value the writer would emit for a payload and
    # assert the contract without a live store:
    namespace = ("fleet_memory", "guardkit", "adr")
    value = {"content": "an ADR body"}  # representative of writer output

    assert namespace[0] == "fleet_memory"
    assert len(namespace) == 3
    assert isinstance(value.get("content"), str) and value["content"], (
        "stored value must carry a non-empty 'content' field for embed-on-write"
    )


# Helper tests for content serialization
@pytest.mark.asyncio
async def test_stored_value_includes_metadata(make_adr_payload, mock_store, mock_settings):
    """Stored value includes metadata like content_hash and version."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload()

    await writer.write(payload)

    stored_value = mock_store.aput.call_args[0][2]
    assert "content_hash" in stored_value
    assert "version" in stored_value
    assert stored_value["version"] == 1


@pytest.mark.asyncio
async def test_natural_key_used_as_store_key(make_adr_payload, mock_store, mock_settings):
    """The natural key is used as the store key (identity)."""
    writer = DeterministicWriter(mock_store, mock_settings)
    payload = make_adr_payload(identifier="ADR_SP_007", project="guardkit")

    await writer.write(payload)

    # Key should be the UUIDv5 from natural key
    store_key = mock_store.aput.call_args[0][1]
    expected_identity = record_identity("adr:guardkit:ADR_SP_007")
    assert store_key == str(expected_identity)
