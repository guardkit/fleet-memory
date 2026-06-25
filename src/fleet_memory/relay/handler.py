"""Thin MEMORY-stream handler: ack/nak/DLQ dispatch for relay ingestion.

The only NATS-aware module in the relay feature. A thin @broker.subscriber
on the MEMORY stream (durable consumer) that wires RelayService.ingest to
JetStream ack semantics. Owns ONLY ack/nak/DLQ routing — delegates ALL
business logic to RelayService.

Ack contract (ack-after-commit):
- await service.ingest(episode) returns cleanly → ACK (write durably committed)
- PoisonEpisodeError → reject/terminate + publish to DLQ with reason
- TransientIngestError (and unenumerated exceptions) → nak for redelivery

Producer: TASK-RLY-006
Consumer: FEAT-MEM-04 (MEMORY stream processing)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from faststream.exceptions import NackMessage, RejectMessage
from faststream.nats import JStream, PullSub
from nats.js.api import AckPolicy, ConsumerConfig

from fleet_memory.errors import PoisonEpisodeError, TransientIngestError
from fleet_memory.relay.schema import MemoryEpisodeV1

if TYPE_CHECKING:
    from fleet_memory.relay.service import RelayService

# Import broker + settings singletons from app (handler never creates either).
# `settings` is None in test environments; fall back to the Settings default.
from fleet_memory.app import broker, settings

logger = logging.getLogger(__name__)

# Service instance set by app.py lifespan (module-level for handler access)
# Initialized as None for type checking; set to real instance in lifespan
service: RelayService | None = None

# --- Durable JetStream consumer wiring (post-Graphiti write-path v2) -----------
# The MEMORY stream (subjects memory.episode.> + memory.dlq.>) is provisioned by
# nats-infrastructure (streams/stream-definitions.json); the relay BINDS to it
# (declare=False) rather than creating it, so stream ownership stays with the infra
# repo and the relay needs no stream-admin permissions. The consumer filters
# memory.episode.> (ingest only — nats-core publishes to
# memory.episode.{project_id}.{episode_type}); poison is published per-project to
# memory.dlq.{project_id}, captured by the same stream and retained for inspection
# but never re-consumed here. A DURABLE PULL consumer makes ack/nak/RejectMessage
# semantics real: clean return -> ack; NackMessage -> nak (redeliver up to
# max_deliver); RejectMessage -> term (no redelivery) + explicit DLQ publish. See
# nats-infrastructure/docs/design/specs/memory-relay/memory-write-path-v2-post-graphiti.md.
MEMORY_SUBJECT = "memory.episode.>"  # consumer filter (matches the publisher's partitioned subjects)
_MAX_DELIVER = settings.max_deliver if settings is not None else 5
# DLQ subject PREFIX (handler appends .{project_id}). Read from the same module-level
# settings singleton as _MAX_DELIVER — that singleton is the single source of truth, so
# the handler needs no broker-context lookup. None in test envs -> Settings default.
_DLQ_SUBJECT = settings.dlq_subject if settings is not None else "memory.dlq"
MEMORY_STREAM = JStream(name="MEMORY", declare=False)
MEMORY_DURABLE = "fleet-memory-relay"
MEMORY_CONSUMER_CONFIG = ConsumerConfig(
    ack_policy=AckPolicy.EXPLICIT,
    max_deliver=_MAX_DELIVER,
    ack_wait=60,  # seconds; deterministic embed + Postgres commit (v2: not the 900s Graphiti window)
)


@broker.subscriber(
    MEMORY_SUBJECT,
    stream=MEMORY_STREAM,
    durable=MEMORY_DURABLE,
    pull_sub=PullSub(batch_size=1),
    config=MEMORY_CONSUMER_CONFIG,
)
async def handle_memory_episode(episode: MemoryEpisodeV1) -> None:
    """Handle memory episode from MEMORY stream with ack/nak/DLQ dispatch.

    Thin handler pattern: delegates ALL business logic to service.ingest,
    owns ONLY ack/nak/DLQ routing based on exception types.

    Ack contract:
    - Clean return → ACK (write committed, no exception raised)
    - PoisonEpisodeError → RejectMessage + publish to DLQ subject
    - TransientIngestError → NackMessage (redelivery up to max_deliver)
    - Unenumerated exceptions → NackMessage (default-to-transient policy)

    Args:
        episode: MemoryEpisodeV1 envelope from MEMORY stream

    Raises:
        RejectMessage: On PoisonEpisodeError (terminates message, routes to DLQ)
        NackMessage: On TransientIngestError or unenumerated exceptions
    """
    # Ensure service is initialized (set by app.py lifespan)
    assert service is not None, "RelayService not initialized in lifespan"

    try:
        # Delegate ALL business logic to service
        # Clean return → implicit ACK
        await service.ingest(episode)

    except PoisonEpisodeError as e:
        # Deterministic failure → reject/terminate + publish to DLQ
        logger.warning(
            "Poison episode rejected: %s (detail: %s)",
            e.reason,
            e.detail,
            extra={"episode_id": episode.episode_id},
        )

        # Publish to the per-project DLQ subject (memory.dlq.{project_id}) with reason
        dlq_base = _DLQ_SUBJECT
        await broker.publish(
            {
                "episode_id": episode.episode_id,
                "project_id": episode.project_id,
                "reason": e.reason,
                "detail": e.detail,
                "content_format": episode.content_format,
                "payload_type": episode.payload_type,
            },
            subject=f"{dlq_base}.{episode.project_id}",
        )

        # Reject/terminate the message (consumer continues)
        raise RejectMessage()

    except TransientIngestError as e:
        # Recoverable failure → nak for redelivery
        logger.info(
            "Transient error, nak for redelivery: %s",
            e.message,
            extra={"episode_id": episode.episode_id},
        )
        raise NackMessage()

    except Exception as e:
        # Default-to-transient: unenumerated exceptions → nak
        # Losing data is worse than redelivering
        logger.error(
            "Unexpected error during ingest, nak for redelivery: %s",
            str(e),
            extra={"episode_id": episode.episode_id},
            exc_info=True,
        )
        raise NackMessage()
