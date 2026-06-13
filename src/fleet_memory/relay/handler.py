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

from fleet_memory.errors import PoisonEpisodeError, TransientIngestError
from fleet_memory.relay.schema import MemoryEpisodeV1

if TYPE_CHECKING:
    from fleet_memory.relay.service import RelayService

# Import broker singleton from app (handler never creates broker)
from fleet_memory.app import broker

logger = logging.getLogger(__name__)

# Service instance set by app.py lifespan (module-level for handler access)
# Initialized as None for type checking; set to real instance in lifespan
service: RelayService | None = None


@broker.subscriber("MEMORY")
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

        # Publish to DLQ subject with reason
        await broker.publish(
            {
                "episode_id": episode.episode_id,
                "project": episode.project,
                "reason": e.reason,
                "detail": e.detail,
                "content_format": episode.content_format,
                "payload_type": episode.payload_type,
            },
            subject=broker.context.get_global("settings").dlq_subject,
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
