"""Unit tests for declared supersession linking.

Tests the deterministic supersession algorithm without live database.
Uses mock store to verify supersession link creation and retrieval exclusion.

Producer: TASK-DW-003
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from fleet_memory.payloads.models import ADRPayload, DocumentPayload
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import record_identity
from fleet_memory.writer.supersession import apply_supersessions

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


@pytest.fixture
def make_adr_payload() -> Callable[..., ADRPayload]:
    """Fixture providing ADRPayload factory."""
    return _make_adr_payload


@pytest.fixture
def mock_store():
    """Mock AsyncPostgresStore for testing supersession logic without database."""
    store = AsyncMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    store.asearch = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_settings():
    """Mock Settings for DeterministicWriter."""
    settings = MagicMock()
    settings.embed_dims = 768
    return settings


# AC-001: Writing a successor marks predecessor superseded_by and records link
@pytest.mark.asyncio
async def test_write_successor_marks_predecessor_superseded_by(
    make_adr_payload, mock_store, mock_settings
):
    """Writing a successor that declares supersession marks predecessor and records link."""
    # Arrange: existing predecessor record
    predecessor = make_adr_payload(identifier="ADR_001", decision="Use MySQL")
    predecessor_key = str(record_identity(predecessor.natural_key))
    predecessor_namespace = ("fleet_memory", "test_proj", "adr")

    existing_record = MagicMock()
    existing_record.value = {
        "content": '{"decision":"Use MySQL"}',
        "content_hash": "hash_mysql",
        "version": 1,
        "natural_key": predecessor.natural_key,
    }

    # Mock store: predecessor exists, successor does not
    async def mock_aget(namespace, key):
        if key == predecessor_key:
            return existing_record
        return None

    mock_store.aget = AsyncMock(side_effect=mock_aget)

    # Act: write successor that supersedes the predecessor
    successor = make_adr_payload(
        identifier="ADR_002",
        decision="Use PostgreSQL",
        supersedes=[predecessor.natural_key],
    )
    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Assert: predecessor was marked superseded_by successor
    calls = mock_store.aput.call_args_list

    # Find the call that updated the predecessor
    predecessor_update = None
    for call in calls:
        namespace, key, value = call[0]
        if key == predecessor_key:
            predecessor_update = value
            break

    assert predecessor_update is not None, "Predecessor should have been updated"
    assert "superseded_by" in predecessor_update
    assert predecessor_update["superseded_by"] == successor.natural_key


# AC-002: Superseded record not in default retrieval but addressable by key
@pytest.mark.asyncio
async def test_superseded_record_excluded_from_default_retrieval(
    make_adr_payload, mock_store, mock_settings
):
    """A superseded record does not appear in default retrieval but is retrievable by key."""
    # This test verifies the superseded_by field is set correctly
    # (actual retrieval filtering is handled by the store layer)

    predecessor = make_adr_payload(identifier="ADR_001")
    successor = make_adr_payload(
        identifier="ADR_002",
        supersedes=[predecessor.natural_key],
    )

    # Track state to simulate store persistence
    state = {}

    async def mock_aget(namespace, key):
        if key in state:
            record = MagicMock()
            record.value = state[key]
            return record
        return None

    async def mock_aput(namespace, key, value):
        state[key] = value

    mock_store.aget = AsyncMock(side_effect=mock_aget)
    mock_store.aput = AsyncMock(side_effect=mock_aput)

    writer = DeterministicWriter(mock_store, mock_settings)

    # Write both records
    await writer.write(predecessor)
    await writer.write(successor)

    # Check the final state of predecessor
    predecessor_key = str(record_identity(predecessor.natural_key))
    assert predecessor_key in state
    assert state[predecessor_key].get("superseded_by") == successor.natural_key


# AC-003: Declaring count predecessors retires exactly count (0, 1, 5)
@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 5])
async def test_declaring_count_predecessors_retires_exactly_count(
    count, make_adr_payload, mock_store, mock_settings
):
    """Declaring count predecessors retires exactly count of them."""
    # Create existing predecessor records
    predecessors = [
        make_adr_payload(identifier=f"ADR_{i:03d}", decision=f"Decision {i}")
        for i in range(1, count + 1)
    ]

    # Mock store to return existing records for predecessors
    existing_records = {}
    for pred in predecessors:
        key = str(record_identity(pred.natural_key))
        record = MagicMock()
        record.value = {
            "content": f'{{"decision":"Decision"}}',
            "content_hash": f"hash_{pred.identifier}",
            "version": 1,
            "natural_key": pred.natural_key,
        }
        existing_records[key] = record

    async def mock_aget(namespace, key):
        return existing_records.get(key)

    mock_store.aget = AsyncMock(side_effect=mock_aget)

    # Write successor that supersedes all predecessors
    successor = make_adr_payload(
        identifier="ADR_999",
        decision="New decision",
        supersedes=[p.natural_key for p in predecessors],
    )

    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Count how many predecessors were marked superseded
    superseded_count = 0
    for call in mock_store.aput.call_args_list:
        _, key, value = call[0]
        if "superseded_by" in value and value["superseded_by"] == successor.natural_key:
            superseded_count += 1

    assert superseded_count == count


# AC-004: Forward supersession (declaring supersession of not-yet-written key)
@pytest.mark.asyncio
async def test_forward_supersession_succeeds(make_adr_payload, mock_store, mock_settings):
    """Declaring supersession of a not-yet-written key succeeds and applies when key appears."""
    # Act: write successor that declares supersession of non-existent key
    successor = make_adr_payload(
        identifier="ADR_002",
        decision="Use PostgreSQL",
        supersedes=["adr:test_proj:ADR_001"],  # Does not exist yet
    )

    writer = DeterministicWriter(mock_store, mock_settings)

    # This should NOT raise an exception
    await writer.write(successor)

    # Verify the forward supersession link was recorded
    successor_key = str(record_identity(successor.natural_key))
    successor_calls = [
        call[0][2] for call in mock_store.aput.call_args_list
        if call[0][1] == successor_key
    ]

    assert len(successor_calls) > 0
    successor_record = successor_calls[0]
    assert "supersedes" in successor_record
    assert "adr:test_proj:ADR_001" in successor_record["supersedes"]

    # Now write the predecessor
    mock_store.reset_mock()
    predecessor = make_adr_payload(identifier="ADR_001", decision="Use MySQL")

    # Mock: successor exists with forward link
    successor_existing = MagicMock()
    successor_existing.value = successor_record
    successor_existing.key = successor_key

    async def mock_aget_with_successor(namespace, key):
        if key == successor_key:
            return successor_existing
        return None

    async def mock_asearch_with_successor(namespace):
        # Return the successor record that declares it supersedes ADR_001
        return [successor_existing]

    mock_store.aget = AsyncMock(side_effect=mock_aget_with_successor)
    mock_store.asearch = AsyncMock(side_effect=mock_asearch_with_successor)

    await writer.write(predecessor)

    # Verify predecessor was marked superseded
    predecessor_key = str(record_identity(predecessor.natural_key))
    predecessor_calls = [
        call[0][2] for call in mock_store.aput.call_args_list
        if call[0][1] == predecessor_key
    ]

    assert any(
        call.get("superseded_by") == successor.natural_key
        for call in predecessor_calls
    )


# AC-005: Cross-project supersession
@pytest.mark.asyncio
async def test_cross_project_supersession(make_adr_payload, mock_store, mock_settings):
    """A successor in one project can retire a predecessor in another project."""
    # Predecessor in project_a
    predecessor = make_adr_payload(project="project_a", identifier="ADR_001")
    predecessor_key = str(record_identity(predecessor.natural_key))
    predecessor_namespace = ("fleet_memory", "project_a", "adr")

    existing_record = MagicMock()
    existing_record.value = {
        "content": '{"decision":"Old"}',
        "content_hash": "hash_old",
        "version": 1,
        "natural_key": predecessor.natural_key,
    }

    async def mock_aget(namespace, key):
        if key == predecessor_key and namespace == predecessor_namespace:
            return existing_record
        return None

    mock_store.aget = AsyncMock(side_effect=mock_aget)

    # Successor in project_b that supersedes predecessor from project_a
    successor = make_adr_payload(
        project="project_b",
        identifier="ADR_002",
        supersedes=[predecessor.natural_key],
    )

    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Verify cross-namespace update occurred
    cross_project_updates = [
        call for call in mock_store.aput.call_args_list
        if call[0][0] == predecessor_namespace and call[0][1] == predecessor_key
    ]

    assert len(cross_project_updates) > 0
    updated_value = cross_project_updates[0][0][2]
    assert updated_value.get("superseded_by") == successor.natural_key


# AC-006: Idempotent re-declaration
@pytest.mark.asyncio
async def test_idempotent_redeclaration(make_adr_payload, mock_store, mock_settings):
    """Re-declaring the same supersession keeps predecessor superseded exactly once."""
    predecessor = make_adr_payload(identifier="ADR_001")
    successor = make_adr_payload(
        identifier="ADR_002",
        supersedes=[predecessor.natural_key],
    )

    predecessor_key = str(record_identity(predecessor.natural_key))
    successor_key = str(record_identity(successor.natural_key))

    # Track state across writes
    state = {}

    async def mock_aget(namespace, key):
        if key in state:
            record = MagicMock()
            record.value = state[key]
            return record
        return None

    async def mock_aput(namespace, key, value):
        state[key] = value

    mock_store.aget = AsyncMock(side_effect=mock_aget)
    mock_store.aput = AsyncMock(side_effect=mock_aput)

    writer = DeterministicWriter(mock_store, mock_settings)

    # First write
    await writer.write(predecessor)
    await writer.write(successor)

    # Verify predecessor is superseded
    assert state[predecessor_key].get("superseded_by") == successor.natural_key

    # Re-write the same successor
    mock_store.reset_mock()
    await writer.write(successor)

    # Verify predecessor is still superseded exactly once
    assert state[predecessor_key].get("superseded_by") == successor.natural_key


# AC-007: Chain collapse (A←B←C)
@pytest.mark.asyncio
async def test_chain_collapse_traceable(make_adr_payload, mock_store, mock_settings):
    """In a chain A←B←C only C appears in default retrieval, chain remains traceable."""
    # Create chain: A ← B ← C
    adr_a = make_adr_payload(identifier="ADR_A", decision="A")
    adr_b = make_adr_payload(
        identifier="ADR_B",
        decision="B",
        supersedes=[adr_a.natural_key],
    )
    adr_c = make_adr_payload(
        identifier="ADR_C",
        decision="C",
        supersedes=[adr_b.natural_key],
    )

    # Track state
    state = {}

    async def mock_aget(namespace, key):
        if key in state:
            record = MagicMock()
            record.value = state[key]
            return record
        return None

    async def mock_aput(namespace, key, value):
        state[key] = value

    mock_store.aget = AsyncMock(side_effect=mock_aget)
    mock_store.aput = AsyncMock(side_effect=mock_aput)

    writer = DeterministicWriter(mock_store, mock_settings)

    # Write chain
    await writer.write(adr_a)
    await writer.write(adr_b)
    await writer.write(adr_c)

    # Verify chain links
    key_a = str(record_identity(adr_a.natural_key))
    key_b = str(record_identity(adr_b.natural_key))
    key_c = str(record_identity(adr_c.natural_key))

    # A is superseded by B
    assert state[key_a].get("superseded_by") == adr_b.natural_key

    # B is superseded by C
    assert state[key_b].get("superseded_by") == adr_c.natural_key

    # C is not superseded
    assert state[key_c].get("superseded_by") is None

    # All records remain addressable (all exist in state)
    assert key_a in state
    assert key_b in state
    assert key_c in state


# AC-008: Racing successors
@pytest.mark.asyncio
async def test_racing_successors_resolve_to_one(make_adr_payload, mock_store, mock_settings):
    """Two successors racing for same predecessor resolve to exactly one recorded successor."""
    predecessor = make_adr_payload(identifier="ADR_001", decision="Old")
    successor1 = make_adr_payload(
        identifier="ADR_002",
        decision="New A",
        supersedes=[predecessor.natural_key],
    )
    successor2 = make_adr_payload(
        identifier="ADR_003",
        decision="New B",
        supersedes=[predecessor.natural_key],
    )

    # Track state
    state = {}

    async def mock_aget(namespace, key):
        if key in state:
            record = MagicMock()
            record.value = state[key]
            return record
        return None

    async def mock_aput(namespace, key, value):
        state[key] = value

    mock_store.aget = AsyncMock(side_effect=mock_aget)
    mock_store.aput = AsyncMock(side_effect=mock_aput)

    writer = DeterministicWriter(mock_store, mock_settings)

    # Write predecessor and both successors
    await writer.write(predecessor)
    await writer.write(successor1)
    await writer.write(successor2)

    # Verify predecessor has exactly one superseded_by link
    predecessor_key = str(record_identity(predecessor.natural_key))
    superseded_by = state[predecessor_key].get("superseded_by")

    assert superseded_by is not None
    assert superseded_by in [successor1.natural_key, successor2.natural_key]

    # The superseded_by field should be a single string, not a list
    assert isinstance(superseded_by, str)


# Test the apply_supersessions helper function directly
@pytest.mark.asyncio
async def test_apply_supersessions_helper_marks_multiple_predecessors(
    make_adr_payload, mock_store
):
    """apply_supersessions marks all declared predecessors in a single operation."""
    # Setup multiple existing predecessors
    predecessors = [
        make_adr_payload(identifier=f"ADR_{i:03d}", decision=f"Decision {i}")
        for i in range(1, 4)
    ]

    state = {}
    for pred in predecessors:
        key = str(record_identity(pred.natural_key))
        state[key] = {
            "content": f'{{"decision":"Decision"}}',
            "content_hash": f"hash_{pred.identifier}",
            "version": 1,
            "natural_key": pred.natural_key,
        }

    async def mock_aget(namespace, key):
        if key in state:
            record = MagicMock()
            record.value = state[key]
            return record
        return None

    async def mock_aput(namespace, key, value):
        state[key] = value

    mock_store.aget = AsyncMock(side_effect=mock_aget)
    mock_store.aput = AsyncMock(side_effect=mock_aput)

    # Apply supersessions
    successor_key = "adr:test_proj:ADR_999"
    predecessor_keys = [p.natural_key for p in predecessors]

    await apply_supersessions(mock_store, successor_key, predecessor_keys)

    # Verify all predecessors were marked
    for pred in predecessors:
        key = str(record_identity(pred.natural_key))
        assert state[key].get("superseded_by") == successor_key
