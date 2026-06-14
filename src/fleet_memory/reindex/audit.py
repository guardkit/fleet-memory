"""Stream-vs-store audit reconciliation for published episodes.

Reconciles published episodes from a RunReport against stored records and
dead-letter records to ensure 100% accounting. Every published episode must
be either stored (writer committed) or recorded on the DLQ subject.

This module provides the audit function that is the enforcement mechanism for
FEAT-MEM-07 AC-3: "no episode is unaccounted for" invariant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from fleet_memory.writer.identity import record_identity

if TYPE_CHECKING:
    pass


class StoreProtocol(Protocol):
    """Protocol for store interface used by audit."""

    async def get(self, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
        """Get a record from the store by namespace and key."""
        ...


class DLQClientProtocol(Protocol):
    """Protocol for DLQ client interface used by audit."""

    async def check_episode_on_dlq(self, episode_id: str) -> bool:
        """Check if an episode ID is on the dead-letter queue."""
        ...


@dataclass(frozen=True)
class AuditResult:
    """Result of auditing published episodes against store and DLQ.

    Attributes:
        total_published: Total number of published episodes from RunReport
        stored_count: Number of episodes found in the store
        dlq_count: Number of episodes found on the DLQ
        unaccounted_count: Number of episodes neither stored nor on DLQ
        unaccounted_episodes: List of natural keys for unaccounted episodes
        is_100_percent_accounted: True if all episodes are accounted for
    """

    total_published: int
    stored_count: int
    dlq_count: int
    unaccounted_count: int
    unaccounted_episodes: list[str]

    @property
    def is_100_percent_accounted(self) -> bool:
        """Check if all published episodes are accounted for.

        Returns:
            True if unaccounted_count is zero, False otherwise
        """
        return self.unaccounted_count == 0


def _derive_episode_id(natural_key: str) -> str:
    """Derive episode ID from natural key using same logic as publisher.

    Must match the derivation in src/fleet_memory/reindex/publisher.py
    to correctly identify DLQ episodes.

    Args:
        natural_key: Three-segment colon-separated key (<type>:<project>:<id>)

    Returns:
        Deterministic 16-character hex string derived from natural_key
    """
    hash_bytes = hashlib.sha256(natural_key.encode("utf-8")).digest()
    return hash_bytes.hex()[:16]


async def audit_published_episodes(
    run_report: Any,
    store: StoreProtocol,
    dlq_client: DLQClientProtocol,
    namespace: tuple[str, ...] = ("fleet_memory",),
) -> AuditResult:
    """Audit published episodes against store and DLQ for 100% accounting.

    Reconciles each published episode from the RunReport:
    - Checks if stored via record_identity(natural_key) lookup
    - Checks if on DLQ via episode_id derived from natural_key
    - Reports any episodes that are neither stored nor dead-lettered

    This is the enforcement mechanism for the "no episode is unaccounted for"
    invariant (FEAT-MEM-07 AC-3).

    Args:
        run_report: RunReport with published_natural_keys list
        store: Store instance supporting get(namespace, key) lookups
        dlq_client: DLQ client supporting check_episode_on_dlq(episode_id)
        namespace: Store namespace tuple (default: ("fleet_memory",))

    Returns:
        AuditResult with counts and list of unaccounted episodes

    Examples:
        >>> # All episodes stored
        >>> result = await audit_published_episodes(report, store, dlq)
        >>> assert result.is_100_percent_accounted
        >>> assert result.unaccounted_count == 0

        >>> # One episode on DLQ (still accounted)
        >>> result = await audit_published_episodes(report, store, dlq)
        >>> assert result.is_100_percent_accounted
        >>> assert result.dlq_count == 1

        >>> # One episode missing (unaccounted - failure)
        >>> result = await audit_published_episodes(report, store, dlq)
        >>> assert not result.is_100_percent_accounted
        >>> assert result.unaccounted_count == 1
    """
    # Extract published natural keys from RunReport
    # RunReport is expected to have published_natural_keys from TASK-RIP-005
    published_natural_keys: list[str] = getattr(
        run_report, "published_natural_keys", []
    )

    total_published = len(published_natural_keys)
    stored_count = 0
    dlq_count = 0
    unaccounted_episodes: list[str] = []

    # Audit each published episode
    for natural_key in published_natural_keys:
        # Check if stored: derive record UUID from natural key
        record_uuid = record_identity(natural_key)
        record = await store.get(namespace, str(record_uuid))

        if record is not None:
            # Episode is stored (writer committed successfully)
            stored_count += 1
            continue

        # Not stored - check if on DLQ
        episode_id = _derive_episode_id(natural_key)
        is_on_dlq = await dlq_client.check_episode_on_dlq(episode_id)

        if is_on_dlq:
            # Episode is on DLQ (poison episode rejected)
            dlq_count += 1
            continue

        # Episode is neither stored nor on DLQ - unaccounted (failure)
        unaccounted_episodes.append(natural_key)

    unaccounted_count = len(unaccounted_episodes)

    return AuditResult(
        total_published=total_published,
        stored_count=stored_count,
        dlq_count=dlq_count,
        unaccounted_count=unaccounted_count,
        unaccounted_episodes=unaccounted_episodes,
    )
