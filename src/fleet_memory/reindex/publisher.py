"""JetStream episode publisher for the re-index pipeline — the vanishing-publish fix.

The previous publisher wrote to subject "MEMORY" through fleet_memory.app.broker: a
core-NATS publish to a subject NO stream captures (the MEMORY stream binds
memory.episode.> and memory.dlq.>), so every "published" episode vanished. This
publisher owns its own JetStream connection built from settings.publish_nats_url
(fail-loud when unset, BEFORE any walking) and publishes to the partitioned subject
``memory.episode.{project}.{payload_type}`` that the relay's durable consumer
actually filters. It NEVER touches fleet_memory.app.broker.

Idempotency: the Nats-Msg-Id header carries the deterministic episode_id
("ep-" + sha256(natural_key)[:16]) so JetStream deduplicates re-publishes.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fleet_memory.payloads.base import BasePayload
    from fleet_memory.settings import Settings

# Body-size guard, mirroring the harvest publisher's MAX_EPISODE_BODY_BYTES:
# oversized payloads are skipped with a named reason, never truncated or crashed on.
MAX_EPISODE_BODY_BYTES = 900 * 1024


class ReindexPublishError(RuntimeError):
    """Raised when the reindex publish path is misconfigured or unavailable."""


def _derive_episode_id(natural_key: str) -> str:
    """Derive deterministic episode_id from natural key.

    Uses SHA-256 hash of natural key to ensure the same payload published twice
    yields the same episode_id for JetStream Msg-Id deduplication. This is the
    ONE rule that mints the id — audit imports it rather than re-stating it
    (a second statement of a rule is a future lie).

    Args:
        natural_key: Three-segment colon-separated key (<type>:<project>:<id>)

    Returns:
        Deterministic episode ID in format "ep-{16-char-hex-prefix}"
    """
    hash_bytes = hashlib.sha256(natural_key.encode("utf-8")).digest()
    return f"ep-{hash_bytes.hex()[:16]}"


def episode_subject(project: str, payload_type: str) -> str:
    """Build the partitioned MEMORY-stream subject for an episode.

    Must match the relay consumer's filter ``memory.episode.>`` — publishing
    anywhere else is a publish nothing captures.
    """
    return f"memory.episode.{project}.{payload_type}"


def build_envelope(payload: BasePayload) -> dict[str, Any]:
    """Build the MemoryEpisodeV1 envelope dict for a payload.

    The envelope carries the canonical ``project_id`` field (the relay schema's
    alias also accepts legacy "project"), episode_type == payload_type,
    content_format="json" (routes to DeterministicWriter, not the prose chunker),
    body as canonical sorted JSON, and source_ref provenance.
    """
    body = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),  # Minimal representation
    )
    return {
        "episode_id": _derive_episode_id(payload.natural_key),
        "project_id": payload.project,
        # episode_type is required on the envelope; the re-index path uses the typed
        # payload key as the coarse source category.
        "episode_type": payload.payload_type,
        "content_format": "json",  # Routes to DeterministicWriter
        "body": body,
        "payload_type": payload.payload_type,
        "source_ref": payload.source_ref,
    }


class ReindexPublisher:
    """JetStream publisher owning its own connection for reindex publish runs.

    Built from settings.publish_nats_url — consumed ONLY by this publish path.
    Fails loud at construction when the URL is unset so a publish run dies
    BEFORE walking, not after processing 70,000 files.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize from settings; fail loud on missing publish URL.

        Args:
            settings: Fleet-memory settings (publish_nats_url required)

        Raises:
            ReindexPublishError: If settings.publish_nats_url is unset
        """
        if not settings.publish_nats_url:
            raise ReindexPublishError(
                "FLEET_MEMORY_PUBLISH_NATS_URL is unset: a publish run has nowhere "
                "to publish. Set it (or use --dry-run for a census without publishing)."
            )
        self._url = settings.publish_nats_url
        self._nc: Any = None
        self._js: Any = None

    async def connect(self) -> None:
        """Open the NATS connection and JetStream context."""
        import nats

        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()

    async def close(self) -> None:
        """Drain and close the NATS connection."""
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None

    async def __aenter__(self) -> ReindexPublisher:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def publish(self, payload: BasePayload) -> str | None:
        """Publish a payload as a MemoryEpisodeV1 to its partitioned subject.

        Args:
            payload: BasePayload instance to publish

        Returns:
            None on success, or a named skip reason (oversized payload) —
            skips are reported, never silent.

        Raises:
            ReindexPublishError: If called before connect()
        """
        if self._js is None:
            raise ReindexPublishError(
                "ReindexPublisher.publish called before connect()"
            )

        envelope = build_envelope(payload)

        body_bytes = len(envelope["body"].encode("utf-8"))
        if body_bytes >= MAX_EPISODE_BODY_BYTES:
            return (
                f"payload body {body_bytes} bytes exceeds "
                f"MAX_EPISODE_BODY_BYTES ({MAX_EPISODE_BODY_BYTES})"
            )

        subject = episode_subject(payload.project, payload.payload_type)
        await self._js.publish(
            subject,
            json.dumps(envelope).encode("utf-8"),
            headers={"Nats-Msg-Id": envelope["episode_id"]},
        )
        return None


# Module-level active publisher: lets the backfill path (which imports
# publish_episode and stays UNTOUCHED) ride the same connection as the corpus run.
_active_publisher: ReindexPublisher | None = None


@asynccontextmanager
async def active_publisher(settings: Settings) -> AsyncIterator[ReindexPublisher]:
    """Context manager wiring a connected ReindexPublisher as the active publisher.

    publish_episode (the backfill compatibility surface) routes through the
    active publisher for the duration of the context.
    """
    global _active_publisher
    publisher = ReindexPublisher(settings)
    await publisher.connect()
    _active_publisher = publisher
    try:
        yield publisher
    finally:
        _active_publisher = None
        await publisher.close()


async def publish_episode(payload: BasePayload) -> None:
    """Publish a BasePayload through the active ReindexPublisher.

    Compatibility surface for the backfill processor (single write path). Publish
    runs establish the active publisher via active_publisher() before walking.

    Args:
        payload: BasePayload instance to publish

    Raises:
        ReindexPublishError: If no active publisher is configured, or the
            payload was skipped (oversize) — backfill payloads are individually
            operator-reviewed, so a skip there is a loud failure, not a report line.
    """
    if _active_publisher is None:
        raise ReindexPublishError(
            "No active ReindexPublisher: publish runs must enter "
            "active_publisher(settings) before publishing episodes."
        )
    skip_reason = await _active_publisher.publish(payload)
    if skip_reason is not None:
        raise ReindexPublishError(
            f"Refusing to publish {payload.natural_key}: {skip_reason}"
        )
