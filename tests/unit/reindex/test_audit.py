"""Unit tests for stream-vs-store audit reconciliation.

Tests cover the audit function that reconciles published episodes against
stored records and dead-letter records to ensure 100% accounting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest

from fleet_memory.reindex.audit import audit_published_episodes


@dataclass(frozen=True)
class MockRunReport:
    """Mock RunReport with published natural keys for testing."""

    published_count: int = 0
    unparseable_count: int = 0
    unrecognized_count: int = 0
    unparseable: list[dict[str, Any]] = field(default_factory=list)
    unrecognized: list[dict[str, Any]] = field(default_factory=list)
    published_natural_keys: list[str] = field(default_factory=list)


class FakeStore:
    """Fake store that simulates record lookups."""

    def __init__(self, stored_ids: set[UUID]) -> None:
        """Initialize with set of stored record IDs.

        Args:
            stored_ids: Set of UUIDs that should be found in the store
        """
        self.stored_ids = stored_ids

    async def get(self, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
        """Return a record if the UUID key is in stored_ids.

        Args:
            namespace: Namespace tuple (ignored in fake)
            key: Record UUID as string

        Returns:
            Fake record dict if UUID is stored, None otherwise
        """
        try:
            uuid_key = UUID(key)
            if uuid_key in self.stored_ids:
                return {"key": key, "value": {"content": "fake"}}
            return None
        except (ValueError, AttributeError):
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
        """Check if an episode ID is on the DLQ.

        Args:
            episode_id: Episode ID to check

        Returns:
            True if episode is on DLQ, False otherwise
        """
        return episode_id in self.dlq_episode_ids


@pytest.mark.asyncio
async def test_all_stored_reports_100_percent() -> None:
    """Test that when all episodes are stored, audit reports 100% accounted."""
    # Given: Three published episodes
    natural_keys = [
        "adr:project1:ADR_001",
        "adr:project1:ADR_002",
        "seed:project2:module_a",
    ]

    run_report = MockRunReport(
        published_count=3,
        published_natural_keys=natural_keys,
    )

    # All episodes are stored (compute their UUIDs)
    from fleet_memory.writer.identity import record_identity

    stored_ids = {record_identity(nk) for nk in natural_keys}
    fake_store = FakeStore(stored_ids)

    # No episodes on DLQ
    fake_dlq = FakeDLQClient(set())

    # When: Running the audit
    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=fake_dlq,
    )

    # Then: All episodes are accounted as stored
    assert result.total_published == 3
    assert result.stored_count == 3
    assert result.dlq_count == 0
    assert result.unaccounted_count == 0
    assert result.unaccounted_episodes == []
    assert result.is_100_percent_accounted


@pytest.mark.asyncio
async def test_dlq_episode_counts_as_accounted() -> None:
    """Test that episodes on the DLQ count as accounted (not failures)."""
    # Given: Two published episodes, one is stored, one is on DLQ
    natural_keys = [
        "adr:project1:ADR_001",
        "adr:project1:ADR_002",  # This one will be on DLQ
    ]

    run_report = MockRunReport(
        published_count=2,
        published_natural_keys=natural_keys,
    )

    from fleet_memory.writer.identity import record_identity

    # Only first episode is stored
    stored_ids = {record_identity(natural_keys[0])}
    fake_store = FakeStore(stored_ids)

    # Second episode is on DLQ (using episode_id from publisher logic)
    import hashlib

    def derive_episode_id(natural_key: str) -> str:
        """Derive episode ID same way publisher does."""
        hash_bytes = hashlib.sha256(natural_key.encode("utf-8")).digest()
        return hash_bytes.hex()[:16]

    dlq_episode_id = derive_episode_id(natural_keys[1])
    fake_dlq = FakeDLQClient({dlq_episode_id})

    # When: Running the audit
    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=fake_dlq,
    )

    # Then: Both episodes are accounted (one stored, one DLQ)
    assert result.total_published == 2
    assert result.stored_count == 1
    assert result.dlq_count == 1
    assert result.unaccounted_count == 0
    assert result.unaccounted_episodes == []
    assert result.is_100_percent_accounted


@pytest.mark.asyncio
async def test_missing_record_reported_unaccounted() -> None:
    """Test that episodes neither stored nor on DLQ are reported as unaccounted."""
    # Given: Three published episodes, only one is stored, one is on DLQ, one is missing
    natural_keys = [
        "adr:project1:ADR_001",  # Will be stored
        "adr:project1:ADR_002",  # Will be on DLQ
        "adr:project1:ADR_003",  # Will be missing (unaccounted)
    ]

    run_report = MockRunReport(
        published_count=3,
        published_natural_keys=natural_keys,
    )

    from fleet_memory.writer.identity import record_identity

    # Only first episode is stored
    stored_ids = {record_identity(natural_keys[0])}
    fake_store = FakeStore(stored_ids)

    # Second episode is on DLQ
    import hashlib

    def derive_episode_id(natural_key: str) -> str:
        """Derive episode ID same way publisher does."""
        hash_bytes = hashlib.sha256(natural_key.encode("utf-8")).digest()
        return hash_bytes.hex()[:16]

    dlq_episode_id = derive_episode_id(natural_keys[1])
    fake_dlq = FakeDLQClient({dlq_episode_id})

    # When: Running the audit
    result = await audit_published_episodes(
        run_report=run_report,
        store=fake_store,
        dlq_client=fake_dlq,
    )

    # Then: One episode is unaccounted (failure)
    assert result.total_published == 3
    assert result.stored_count == 1
    assert result.dlq_count == 1
    assert result.unaccounted_count == 1
    assert len(result.unaccounted_episodes) == 1
    assert result.unaccounted_episodes[0] == natural_keys[2]
    assert not result.is_100_percent_accounted
