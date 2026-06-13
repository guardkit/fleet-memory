"""Unit tests for writer supersession behavior.

Tests the deterministic supersession algorithm using mock store (no infrastructure).
Covers all supersession scenarios: link creation, forward supersession, cross-project,
idempotent re-declaration, chain collapse, and racing successors.

Producer: TASK-DW-005
Consumer: TASK-DW-003 validation
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleet_memory.payloads.models import ADRPayload
from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import record_identity

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
    """Mock AsyncPostgresStore for testing supersession without database."""
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


# AC-001: Supersede-and-link and excluded-but-addressable
@pytest.mark.asyncio
async def test_supersede_and_link_marks_predecessor(
    make_adr_payload, mock_store, mock_settings
):
    """Writing successor marks predecessor superseded_by and records link."""
    # Arrange: existing predecessor
    predecessor = make_adr_payload(identifier="ADR_001", decision="Use MySQL")
    predecessor_key = str(record_identity(predecessor.natural_key))

    existing_record = MagicMock()
    existing_record.value = {
        "content": '{"decision":"Use MySQL"}',
        "content_hash": "hash_mysql",
        "version": 1,
        "natural_key": predecessor.natural_key,
    }

    async def mock_aget(namespace, key):
        return existing_record if key == predecessor_key else None

    mock_store.aget = AsyncMock(side_effect=mock_aget)

    # Act: write successor that supersedes predecessor
    successor = make_adr_payload(
        identifier="ADR_002",
        decision="Use PostgreSQL",
        supersedes=[predecessor.natural_key],
    )
    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Assert: predecessor was marked superseded_by successor
    predecessor_update = None
    for call in mock_store.aput.call_args_list:
        namespace, key, value = call[0]
        if key == predecessor_key:
            predecessor_update = value
            break

    assert predecessor_update is not None
    assert predecessor_update["superseded_by"] == successor.natural_key


@pytest.mark.asyncio
async def test_superseded_record_excluded_but_addressable(
    make_adr_payload, mock_store, mock_settings
):
    """Superseded record has superseded_by field set for exclusion from default retrieval."""
    predecessor = make_adr_payload(identifier="ADR_001")
    successor = make_adr_payload(
        identifier="ADR_002", supersedes=[predecessor.natural_key]
    )

    # Simulate persistent state
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
    await writer.write(predecessor)
    await writer.write(successor)

    # Verify predecessor marked as superseded
    predecessor_key = str(record_identity(predecessor.natural_key))
    assert state[predecessor_key]["superseded_by"] == successor.natural_key


# AC-002: Supersession-count outline (0, 1, 5)
@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 5])
async def test_supersession_count_outline(
    count, make_adr_payload, mock_store, mock_settings
):
    """Declaring count predecessors retires exactly count of them."""
    # Create predecessors
    predecessors = [
        make_adr_payload(identifier=f"ADR_{i:03d}", decision=f"Decision {i}")
        for i in range(1, count + 1)
    ]

    # Mock existing records
    existing_records = {}
    for pred in predecessors:
        key = str(record_identity(pred.natural_key))
        record = MagicMock()
        record.value = {
            "content": '{"decision":"Decision"}',
            "content_hash": f"hash_{pred.identifier}",
            "version": 1,
            "natural_key": pred.natural_key,
        }
        existing_records[key] = record

    async def mock_aget(namespace, key):
        return existing_records.get(key)

    mock_store.aget = AsyncMock(side_effect=mock_aget)

    # Write successor superseding all predecessors
    successor = make_adr_payload(
        identifier="ADR_999",
        decision="New decision",
        supersedes=[p.natural_key for p in predecessors],
    )

    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Count superseded predecessors
    superseded_count = sum(
        1
        for call in mock_store.aput.call_args_list
        if call[0][2].get("superseded_by") == successor.natural_key
    )

    assert superseded_count == count


# AC-003: Forward supersession (ASSUM-008)
@pytest.mark.asyncio
async def test_forward_supersession_applied_when_key_appears(
    make_adr_payload, mock_store, mock_settings
):
    """Declaring supersession of not-yet-written key succeeds and applies when key appears."""
    # Act: write successor declaring supersession of non-existent key
    successor = make_adr_payload(
        identifier="ADR_002",
        decision="Use PostgreSQL",
        supersedes=["adr:test_proj:ADR_001"],
    )

    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Verify forward link recorded
    successor_key = str(record_identity(successor.natural_key))
    successor_calls = [
        call[0][2]
        for call in mock_store.aput.call_args_list
        if call[0][1] == successor_key
    ]

    assert len(successor_calls) > 0
    assert "adr:test_proj:ADR_001" in successor_calls[0]["supersedes"]

    # Now write the predecessor
    mock_store.reset_mock()
    predecessor = make_adr_payload(identifier="ADR_001", decision="Use MySQL")

    # Mock successor exists with forward link
    successor_existing = MagicMock()
    successor_existing.value = successor_calls[0]
    successor_existing.key = successor_key

    async def mock_asearch_with_successor(namespace):
        return [successor_existing]

    mock_store.asearch = AsyncMock(side_effect=mock_asearch_with_successor)

    await writer.write(predecessor)

    # Verify predecessor marked superseded
    predecessor_key = str(record_identity(predecessor.natural_key))
    predecessor_calls = [
        call[0][2]
        for call in mock_store.aput.call_args_list
        if call[0][1] == predecessor_key
    ]

    assert any(
        call.get("superseded_by") == successor.natural_key for call in predecessor_calls
    )


# AC-004: Cross-project supersession
@pytest.mark.asyncio
async def test_cross_project_supersession(
    make_adr_payload, mock_store, mock_settings
):
    """Successor in one project can retire predecessor in another project."""
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
        return existing_record if (
            key == predecessor_key and namespace == predecessor_namespace
        ) else None

    mock_store.aget = AsyncMock(side_effect=mock_aget)

    # Successor in project_b superseding predecessor from project_a
    successor = make_adr_payload(
        project="project_b",
        identifier="ADR_002",
        supersedes=[predecessor.natural_key],
    )

    writer = DeterministicWriter(mock_store, mock_settings)
    await writer.write(successor)

    # Verify cross-namespace update
    cross_updates = [
        call
        for call in mock_store.aput.call_args_list
        if call[0][0] == predecessor_namespace and call[0][1] == predecessor_key
    ]

    assert len(cross_updates) > 0
    assert cross_updates[0][0][2]["superseded_by"] == successor.natural_key


# AC-005: Idempotent re-declaration
@pytest.mark.asyncio
async def test_idempotent_redeclaration(
    make_adr_payload, mock_store, mock_settings
):
    """Re-declaring same supersession keeps predecessor superseded exactly once."""
    predecessor = make_adr_payload(identifier="ADR_001")
    successor = make_adr_payload(
        identifier="ADR_002", supersedes=[predecessor.natural_key]
    )

    # Simulate persistent state
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

    predecessor_key = str(record_identity(predecessor.natural_key))
    assert state[predecessor_key]["superseded_by"] == successor.natural_key

    # Re-write successor
    mock_store.reset_mock()
    await writer.write(successor)

    # Verify still superseded exactly once
    assert state[predecessor_key]["superseded_by"] == successor.natural_key


# AC-006: Chain collapse (A←B←C)
@pytest.mark.asyncio
async def test_chain_collapse_traceable(
    make_adr_payload, mock_store, mock_settings
):
    """Chain A←B←C: only C in default retrieval, chain traceable back to A."""
    # Create chain
    adr_a = make_adr_payload(identifier="ADR_A", decision="A")
    adr_b = make_adr_payload(
        identifier="ADR_B", decision="B", supersedes=[adr_a.natural_key]
    )
    adr_c = make_adr_payload(
        identifier="ADR_C", decision="C", supersedes=[adr_b.natural_key]
    )

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

    assert state[key_a]["superseded_by"] == adr_b.natural_key
    assert state[key_b]["superseded_by"] == adr_c.natural_key
    assert state[key_c].get("superseded_by") is None

    # All records remain addressable
    assert all(k in state for k in [key_a, key_b, key_c])


# AC-007: Racing successors
@pytest.mark.asyncio
async def test_racing_successors_resolve_to_one(
    make_adr_payload, mock_store, mock_settings
):
    """Racing successors for same predecessor resolve to exactly one successor."""
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

    # Verify exactly one superseded_by link (last write wins)
    predecessor_key = str(record_identity(predecessor.natural_key))
    superseded_by = state[predecessor_key]["superseded_by"]

    assert superseded_by is not None
    assert superseded_by in [successor1.natural_key, successor2.natural_key]
    assert isinstance(superseded_by, str)
