"""Unit tests for stream-vs-store audit reconciliation.

Tests cover the audit function that reconciles published episodes against
stored records and dead-letter records to ensure 100% accounting.

The fakes here previously encoded the unprefixed episode_id drift (sha256 hex
WITHOUT "ep-"): every DLQ hit would have read UNACCOUNTED. One rule mints the
id — the fakes now import the publisher's _derive_episode_id like the audit does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fleet_memory.reindex.audit import audit_published_episodes
from fleet_memory.reindex.dlq_client import JetStreamDLQClient, parse_episode_id
from fleet_memory.reindex.publisher import _derive_episode_id, build_envelope
from fleet_memory.writer.identity import record_identity


@dataclass(frozen=True)
class MockRunReport:
    """Mock RunReport with published natural keys for testing."""

    published_count: int = 0
    unparseable_count: int = 0
    skipped_count: int = 0
    unparseable: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    published_natural_keys: list[str] = field(default_factory=list)


class FakeStore:
    """Fake store simulating AsyncPostgresStore.aget lookups.

    Records the namespaces queried so tests can assert the audit derives the
    namespace PER KEY (("fleet_memory", project, payload_type)).
    """

    def __init__(self, stored: dict[tuple[str, ...], set[UUID]]) -> None:
        """Initialize with stored record UUIDs per namespace.

        Args:
            stored: Mapping of namespace tuple -> set of stored record UUIDs
        """
        self.stored = stored
        self.queried_namespaces: list[tuple[str, ...]] = []

    async def aget(self, namespace: tuple[str, ...], key: str) -> Any | None:
        """Return a stub item if the UUID key is stored under the namespace."""
        self.queried_namespaces.append(namespace)
        try:
            uuid_key = UUID(key)
        except (ValueError, AttributeError):
            return None
        if uuid_key in self.stored.get(namespace, set()):
            return {"key": key, "value": {"content": "fake"}}
        return None


class FakeDLQClient:
    """Fake DLQ client that simulates dead-letter episode lookups."""

    def __init__(self, dlq_episode_ids: set[str]) -> None:
        """Initialize with set of episode IDs on the DLQ.

        Args:
            dlq_episode_ids: Set of episode IDs that are on the dead-letter queue
        """
        self.dlq_episode_ids = dlq_episode_ids

    async def check_episode_on_dlq(self, episode_id: str) -> bool:
        """Check if an episode ID is on the DLQ."""
        return episode_id in self.dlq_episode_ids


def _store_with(natural_keys: list[str]) -> FakeStore:
    """Build a FakeStore holding each natural key in ITS derived namespace."""
    stored: dict[tuple[str, ...], set[UUID]] = {}
    for natural_key in natural_keys:
        payload_type, project, _ = natural_key.split(":")
        namespace = ("fleet_memory", project, payload_type)
        stored.setdefault(namespace, set()).add(record_identity(natural_key))
    return FakeStore(stored)


async def test_all_stored_reports_100_percent() -> None:
    """When all episodes are stored, audit reports 100% accounted."""
    natural_keys = [
        "build_outcome:guardkit:TASK_001",
        "build_outcome:guardkit:TASK_002",
        "adr:project2:ADR_001",
    ]

    run_report = MockRunReport(
        published_count=3,
        published_natural_keys=natural_keys,
    )

    fake_store = _store_with(natural_keys)
    fake_dlq = FakeDLQClient(set())

    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=fake_dlq,
    )

    assert result.total_published == 3
    assert result.stored_count == 3
    assert result.dlq_count == 0
    assert result.unaccounted_count == 0
    assert result.unaccounted_episodes == []
    assert result.is_100_percent_accounted


async def test_namespace_derived_per_key() -> None:
    """The audit looks each key up in ITS ("fleet_memory", project, type)
    namespace — a single namespace parameter would miss every record."""
    natural_keys = [
        "build_outcome:guardkit:TASK_001",
        "adr:other_project:ADR_009",
    ]
    run_report = MockRunReport(published_natural_keys=natural_keys)
    fake_store = _store_with(natural_keys)

    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=FakeDLQClient(set()),
    )

    assert result.stored_count == 2
    assert fake_store.queried_namespaces == [
        ("fleet_memory", "guardkit", "build_outcome"),
        ("fleet_memory", "other_project", "adr"),
    ]


async def test_dlq_episode_counts_as_accounted() -> None:
    """Episodes on the DLQ count as accounted (not failures).

    The DLQ set carries PREFIXED episode ids ("ep-" + 16 hex) exactly as the
    publisher mints them — the drift this test previously encoded (unprefixed)
    made every DLQ hit unaccounted.
    """
    natural_keys = [
        "build_outcome:guardkit:TASK_001",
        "build_outcome:guardkit:TASK_002",  # This one will be on DLQ
    ]

    run_report = MockRunReport(
        published_count=2,
        published_natural_keys=natural_keys,
    )

    fake_store = _store_with(natural_keys[:1])

    # DLQ id minted by the publisher's ONE rule
    dlq_episode_id = _derive_episode_id(natural_keys[1])
    assert dlq_episode_id.startswith("ep-")
    fake_dlq = FakeDLQClient({dlq_episode_id})

    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=fake_dlq,
    )

    assert result.total_published == 2
    assert result.stored_count == 1
    assert result.dlq_count == 1
    assert result.unaccounted_count == 0
    assert result.unaccounted_episodes == []
    assert result.is_100_percent_accounted


async def test_missing_record_reported_unaccounted() -> None:
    """Episodes neither stored nor on DLQ are reported as unaccounted."""
    natural_keys = [
        "build_outcome:guardkit:TASK_001",  # Will be stored
        "build_outcome:guardkit:TASK_002",  # Will be on DLQ
        "build_outcome:guardkit:TASK_003",  # Will be missing (unaccounted)
    ]

    run_report = MockRunReport(
        published_count=3,
        published_natural_keys=natural_keys,
    )

    fake_store = _store_with(natural_keys[:1])
    fake_dlq = FakeDLQClient({_derive_episode_id(natural_keys[1])})

    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=fake_dlq,
    )

    assert result.total_published == 3
    assert result.stored_count == 1
    assert result.dlq_count == 1
    assert result.unaccounted_count == 1
    assert result.unaccounted_episodes == ["build_outcome:guardkit:TASK_003"]
    assert not result.is_100_percent_accounted


async def test_round_trip_poison_episode_publisher_to_dlq_to_audit() -> None:
    """Round trip: publisher envelope -> handler-shaped DLQ payload -> audit.

    One poison episode: the publisher mints its episode_id; the relay's
    handler._publish_dlq puts that id in the JSON BODY of the DLQ message;
    JetStreamDLQClient parses it from there; the audit counts dlq_count==1.
    """
    import json

    from fleet_memory.payloads.models import BuildOutcomePayload

    payload = BuildOutcomePayload(
        project="guardkit",
        identifier="TASK_POISON",
        status="success",
        duration_seconds=0,
        source_ref="tasks/completed/TASK-POISON.md",
    )
    envelope = build_envelope(payload)

    # Handler-shaped DLQ payload (mirrors relay.handler._publish_dlq)
    dlq_payload = json.dumps(
        {
            "episode_id": envelope["episode_id"],
            "project_id": envelope["project_id"],
            "reason": "poison",
            "detail": "identifier validation failed",
            "content_format": envelope["content_format"],
            "payload_type": envelope["payload_type"],
        }
    ).encode("utf-8")

    # The DLQ client parses the id from the message BODY
    assert parse_episode_id(dlq_payload) == envelope["episode_id"]

    class _Settings:
        nats_url = "nats://unused:4222"
        dlq_subject = "memory.dlq"

    dlq_client = JetStreamDLQClient(_Settings(), "guardkit")
    dlq_client.ingest([dlq_payload])

    run_report = MockRunReport(
        published_count=1,
        published_natural_keys=[payload.natural_key],
    )
    fake_store = FakeStore({})  # Not stored anywhere — the writer rejected it

    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=dlq_client,
    )

    assert result.dlq_count == 1
    assert result.unaccounted_count == 0
    assert result.is_100_percent_accounted
