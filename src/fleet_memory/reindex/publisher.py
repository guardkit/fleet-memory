"""Episode publisher for re-index pipeline.

Converts BasePayload instances to MemoryEpisodeV1 messages with content_format="json"
and publishes to the MEMORY stream. This is the single write path for structured
payloads entering the memory system.

Producer: TASK-RIP-002
Consumer: RelayService (routes JSON episodes to DeterministicWriter)
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from fleet_memory.app import broker

if TYPE_CHECKING:
    from fleet_memory.payloads.base import BasePayload


def _derive_episode_id(natural_key: str) -> str:
    """Derive deterministic episode_id from natural key.

    Uses SHA-256 hash of natural key to ensure the same payload published twice
    yields the same episode_id for JetStream Msg-Id deduplication.

    Args:
        natural_key: Three-segment colon-separated key (<type>:<project>:<id>)

    Returns:
        Deterministic episode ID derived from natural key
    """
    hash_bytes = hashlib.sha256(natural_key.encode("utf-8")).digest()
    return f"ep-{hash_bytes.hex()[:16]}"


async def publish_episode(payload: BasePayload) -> None:
    """Publish a BasePayload as a MemoryEpisodeV1 to the MEMORY stream.

    Converts the payload to a JSON-formatted episode with routing metadata,
    then publishes to the MEMORY stream for relay processing.

    The episode has:
    - content_format="json" (routes to DeterministicWriter, not prose chunker)
    - episode_type=payload.payload_type (required coarse source category; for the
      re-index path the typed-payload key doubles as the episode category)
    - payload_type=payload.payload_type (for registry dispatch)
    - body=canonical JSON serialization (round-trips through registry)
    - episode_id=deterministic hash of natural_key (idempotent publish)
    - source_ref=payload.source_ref (provenance tracking)

    Args:
        payload: BasePayload instance to publish

    Raises:
        None: Publishes to broker, broker handles connectivity errors
    """
    # Derive deterministic episode_id from natural key
    episode_id = _derive_episode_id(payload.natural_key)

    # Serialize payload to canonical JSON (sorted keys for stability)
    body = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),  # Minimal representation
    )

    # Construct MemoryEpisodeV1 envelope
    episode_data = {
        "episode_id": episode_id,
        "project": payload.project,
        # episode_type is required on the envelope; the re-index path uses the typed
        # payload key as the coarse source category (adr/feature_outcome/...).
        "episode_type": payload.payload_type,
        "content_format": "json",  # Routes to DeterministicWriter
        "body": body,
        "payload_type": payload.payload_type,
        "source_ref": payload.source_ref,
    }

    # Publish to MEMORY stream
    await broker.publish(episode_data, subject="MEMORY")
