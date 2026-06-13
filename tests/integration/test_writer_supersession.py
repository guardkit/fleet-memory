"""Integration tests for writer supersession against real PostgreSQL.

Marker-gated (@pytest.mark.integration) tests validating supersession behavior
against ephemeral Postgres+pgvector. Tests supersede-and-link, forward supersession,
cross-project supersession, chain collapse, and racing successors.

Requirements:
- Docker running for ephemeral_pg fixture
- Run with: pytest -m integration tests/integration/test_writer_supersession.py

Producer: TASK-DW-005
Consumer: TASK-DW-003 validation
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from fleet_memory.payloads.models import ADRPayload
from fleet_memory.settings import Settings
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
def settings_fixture(test_settings) -> Settings:
    """Pass through test_settings from conftest."""
    return test_settings


# AC-001: Supersede-and-link and excluded-but-addressable
@pytest.mark.integration
async def test_supersede_and_link_with_real_store(
    make_adr_payload, store_context, settings_fixture
):
    """Writing successor marks predecessor superseded_by in real Postgres."""
    store, _ = store_context

    # Write predecessor
    predecessor = make_adr_payload(identifier="ADR_001", decision="Use MySQL")
    writer = DeterministicWriter(store, settings_fixture)
    await writer.write(predecessor)

    # Build correct namespace from payload
    namespace = ("fleet_memory", predecessor.project, predecessor.payload_type)

    # Verify predecessor exists and is not superseded
    predecessor_key = str(record_identity(predecessor.natural_key))
    record = await store.aget(namespace, predecessor_key)
    assert record is not None
    assert record.value.get("superseded_by") is None

    # Write successor that supersedes predecessor
    successor = make_adr_payload(
        identifier="ADR_002",
        decision="Use PostgreSQL",
        supersedes=[predecessor.natural_key],
    )
    await writer.write(successor)

    # Verify predecessor marked superseded
    record = await store.aget(namespace, predecessor_key)
    assert record is not None
    assert record.value["superseded_by"] == successor.natural_key


@pytest.mark.integration
async def test_superseded_record_addressable_by_key(
    make_adr_payload, store_context, settings_fixture
):
    """Superseded record remains addressable by direct key lookup."""
    store, _ = store_context

    predecessor = make_adr_payload(identifier="ADR_001")
    successor = make_adr_payload(
        identifier="ADR_002", supersedes=[predecessor.natural_key]
    )

    writer = DeterministicWriter(store, settings_fixture)
    await writer.write(predecessor)
    await writer.write(successor)

    # Build correct namespace from payload
    namespace = ("fleet_memory", predecessor.project, predecessor.payload_type)

    # Direct lookup by key succeeds
    predecessor_key = str(record_identity(predecessor.natural_key))
    record = await store.aget(namespace, predecessor_key)
    assert record is not None
    assert record.value["superseded_by"] == successor.natural_key


# AC-002: Supersession-count outline
@pytest.mark.integration
@pytest.mark.parametrize("count", [0, 1, 5])
async def test_supersession_count_with_real_store(
    count, make_adr_payload, store_context, settings_fixture
):
    """Declaring count predecessors retires exactly count in real Postgres."""
    store, _ = store_context

    # Create and write predecessors
    predecessors = [
        make_adr_payload(identifier=f"ADR_{i:03d}", decision=f"Decision {i}")
        for i in range(1, count + 1)
    ]

    writer = DeterministicWriter(store, settings_fixture)
    for pred in predecessors:
        await writer.write(pred)

    # Write successor superseding all
    successor = make_adr_payload(
        identifier="ADR_999",
        decision="New decision",
        supersedes=[p.natural_key for p in predecessors],
    )
    await writer.write(successor)

    # Build correct namespace from payload
    namespace = ("fleet_memory", successor.project, successor.payload_type)

    # Verify each predecessor is superseded
    for pred in predecessors:
        key = str(record_identity(pred.natural_key))
        record = await store.aget(namespace, key)
        assert record is not None
        assert record.value["superseded_by"] == successor.natural_key


# AC-003: Forward supersession
@pytest.mark.integration
async def test_forward_supersession_with_real_store(
    make_adr_payload, store_context, settings_fixture
):
    """Forward supersession link applied when predecessor written after successor."""
    store, _ = store_context

    # Write successor declaring supersession of non-existent key
    successor = make_adr_payload(
        identifier="ADR_002",
        decision="Use PostgreSQL",
        supersedes=["adr:test_proj:ADR_001"],
    )

    writer = DeterministicWriter(store, settings_fixture)
    await writer.write(successor)

    # Build correct namespace from payload
    namespace = ("fleet_memory", successor.project, successor.payload_type)

    # Verify successor has forward link
    successor_key = str(record_identity(successor.natural_key))
    record = await store.aget(namespace, successor_key)
    assert record is not None
    assert "adr:test_proj:ADR_001" in record.value["supersedes"]

    # Now write the predecessor
    predecessor = make_adr_payload(identifier="ADR_001", decision="Use MySQL")
    await writer.write(predecessor)

    # Verify predecessor marked superseded
    predecessor_key = str(record_identity(predecessor.natural_key))
    record = await store.aget(namespace, predecessor_key)
    assert record is not None
    assert record.value["superseded_by"] == successor.natural_key


# AC-004: Cross-project supersession
@pytest.mark.integration
async def test_cross_project_supersession_with_real_store(
    make_adr_payload, store_context, settings_fixture
):
    """Successor in one project can retire predecessor from another project."""
    store, _ = store_context

    # Write predecessor in project_a
    predecessor = make_adr_payload(project="project_a", identifier="ADR_001")
    predecessor_namespace = ("fleet_memory", "project_a", "adr")

    writer = DeterministicWriter(store, settings_fixture)
    await writer.write(predecessor)

    # Write successor in project_b superseding predecessor
    successor = make_adr_payload(
        project="project_b",
        identifier="ADR_002",
        supersedes=[predecessor.natural_key],
    )
    await writer.write(successor)

    # Verify predecessor in project_a is marked superseded
    predecessor_key = str(record_identity(predecessor.natural_key))
    record = await store.aget(predecessor_namespace, predecessor_key)
    assert record is not None
    assert record.value["superseded_by"] == successor.natural_key


# AC-005: Idempotent re-declaration
@pytest.mark.integration
async def test_idempotent_redeclaration_with_real_store(
    make_adr_payload, store_context, settings_fixture
):
    """Re-declaring same supersession is idempotent in real Postgres."""
    store, _ = store_context

    predecessor = make_adr_payload(identifier="ADR_001")
    successor = make_adr_payload(
        identifier="ADR_002", supersedes=[predecessor.natural_key]
    )

    writer = DeterministicWriter(store, settings_fixture)

    # First write
    await writer.write(predecessor)
    await writer.write(successor)

    # Build correct namespace from payload
    namespace = ("fleet_memory", predecessor.project, predecessor.payload_type)

    predecessor_key = str(record_identity(predecessor.natural_key))
    first_record = await store.aget(namespace, predecessor_key)
    assert first_record is not None
    first_superseded_by = first_record.value["superseded_by"]

    # Re-write successor (idempotent no-op due to content hash)
    await writer.write(successor)

    # Verify predecessor still superseded exactly once
    second_record = await store.aget(namespace, predecessor_key)
    assert second_record is not None
    assert second_record.value["superseded_by"] == first_superseded_by


# AC-006: Chain collapse
@pytest.mark.integration
async def test_chain_collapse_traceable_with_real_store(
    make_adr_payload, store_context, settings_fixture
):
    """Chain A←B←C: only C unsuperseded, chain traceable in real Postgres."""
    store, _ = store_context

    # Create and write chain
    adr_a = make_adr_payload(identifier="ADR_A", decision="A")
    adr_b = make_adr_payload(
        identifier="ADR_B", decision="B", supersedes=[adr_a.natural_key]
    )
    adr_c = make_adr_payload(
        identifier="ADR_C", decision="C", supersedes=[adr_b.natural_key]
    )

    writer = DeterministicWriter(store, settings_fixture)
    await writer.write(adr_a)
    await writer.write(adr_b)
    await writer.write(adr_c)

    # Build correct namespace from payload
    namespace = ("fleet_memory", adr_a.project, adr_a.payload_type)

    # Verify chain links
    key_a = str(record_identity(adr_a.natural_key))
    key_b = str(record_identity(adr_b.natural_key))
    key_c = str(record_identity(adr_c.natural_key))

    record_a = await store.aget(namespace, key_a)
    record_b = await store.aget(namespace, key_b)
    record_c = await store.aget(namespace, key_c)

    assert record_a.value["superseded_by"] == adr_b.natural_key
    assert record_b.value["superseded_by"] == adr_c.natural_key
    assert record_c.value.get("superseded_by") is None

    # All records remain addressable
    assert all(r is not None for r in [record_a, record_b, record_c])


# AC-007: Racing successors
@pytest.mark.integration
async def test_racing_successors_with_real_store(
    make_adr_payload, store_context, settings_fixture
):
    """Racing successors resolve to exactly one in real Postgres."""
    store, _ = store_context

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

    writer = DeterministicWriter(store, settings_fixture)

    # Write predecessor
    await writer.write(predecessor)

    # Race: write both successors concurrently
    await asyncio.gather(
        writer.write(successor1),
        writer.write(successor2),
    )

    # Build correct namespace from payload
    namespace = ("fleet_memory", predecessor.project, predecessor.payload_type)

    # Verify exactly one superseded_by link (last write wins)
    predecessor_key = str(record_identity(predecessor.natural_key))
    record = await store.aget(namespace, predecessor_key)
    assert record is not None

    superseded_by = record.value["superseded_by"]
    assert superseded_by in [successor1.natural_key, successor2.natural_key]
    assert isinstance(superseded_by, str)
