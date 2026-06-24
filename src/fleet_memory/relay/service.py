"""RelayService: content_format routing and two-layer idempotency.

The brain of the relay with zero NATS imports (pure service — testable by direct instantiation).
Routes episodes based on content_format (json/markdown/text) and maps exceptions to
poison (deterministic failures) vs transient (recoverable failures).

Producer: TASK-RLY-005
Consumer: FEAT-MEM-04 (relay ingestion)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import ValidationError

from fleet_memory.errors import (
    EmbedDimensionError,
    EmbedServiceError,
    EmbedTimeoutError,
    NamespaceValidationError,
    PoisonEpisodeError,
    TransientIngestError,
    UnknownPayloadTypeError,
)
from fleet_memory.payloads.base import IdentifierValidationError
from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.relay.chunker import chunk_prose

if TYPE_CHECKING:
    from fleet_memory.relay.chunk_writer import ChunkWriter
    from fleet_memory.relay.schema import MemoryEpisodeV1
    from fleet_memory.settings import Settings
    from fleet_memory.writer.core import DeterministicWriter


class RelayService:
    """Pure service for memory episode ingestion with content_format routing.

    Routes episodes based on content_format:
    - json → typed payload via registry → DeterministicWriter (idempotency layer 1)
    - markdown/text → chunk_prose → ChunkWriter (idempotency layer 2)
    - anything else → PoisonEpisodeError

    Exception mapping (correctness core):
    - Deterministic failures → PoisonEpisodeError (DLQ)
    - Recoverable failures → TransientIngestError (nak + redeliver)
    - Unenumerated exceptions → TransientIngestError (default-to-transient policy)

    Args:
        writer: DeterministicWriter for structured json payloads
        chunk_writer: ChunkWriter for prose chunks
        settings: Configuration (chunking params, etc.)
    """

    def __init__(
        self,
        writer: DeterministicWriter,
        chunk_writer: ChunkWriter,
        settings: Settings,
    ) -> None:
        """Initialize service with collaborators.

        Args:
            writer: DeterministicWriter instance
            chunk_writer: ChunkWriter instance
            settings: Settings instance
        """
        self.writer = writer
        self.chunk_writer = chunk_writer
        self.settings = settings

    async def ingest(self, episode: MemoryEpisodeV1) -> None:
        """Ingest a memory episode with content_format-based routing.

        Routes based on episode.content_format:
        - "json" → _ingest_json (structured path)
        - "markdown" or "text" → _ingest_prose (chunking path)
        - anything else → PoisonEpisodeError

        Returns only after durable write commits. Clean return signals handler to ack.

        Args:
            episode: MemoryEpisodeV1 envelope from NATS stream

        Raises:
            PoisonEpisodeError: Deterministic failure (unparseable, validation,
                unknown type/format, namespace violation, dimension mismatch)
            TransientIngestError: Recoverable failure (service unavailable,
                timeout, connection error, or any unenumerated exception)
        """
        try:
            # Route based on content_format
            if episode.content_format == "json":
                await self._ingest_json(episode)
            elif episode.content_format in ("markdown", "text"):
                await self._ingest_prose(episode)
            else:
                # Unrecognized format → poison
                raise PoisonEpisodeError(
                    reason=f"unrecognized content_format: {episode.content_format}",
                    detail="Only json, markdown, and text are supported",
                )

        # Exception mapping: deterministic failures → PoisonEpisodeError
        except PoisonEpisodeError:
            # Already poison, re-raise as-is
            raise
        except UnknownPayloadTypeError as e:
            # Unknown payload_type → poison
            raise PoisonEpisodeError(
                reason=f"unknown payload_type: {e.payload_type}",
                detail="Not found in dispatch registry",
            ) from e
        except NamespaceValidationError as e:
            # Hyphenated project or invalid namespace → poison
            raise PoisonEpisodeError(
                reason=f"invalid namespace: {e.invalid_parts}",
                detail=f"Namespace {e.namespace} contains invalid identifiers",
            ) from e
        except IdentifierValidationError as e:
            # Invalid project or identifier (hyphens, etc.) → poison
            raise PoisonEpisodeError(
                reason=f"invalid {e.field_name} identifier: {e.value}",
                detail="Identifiers must use underscores only",
            ) from e
        except ValidationError as e:
            # Pydantic validation failure → poison
            raise PoisonEpisodeError(
                reason="payload validation failed",
                detail=str(e),
            ) from e
        except EmbedDimensionError as e:
            # Wrong dimension → poison (deterministic config mismatch)
            raise PoisonEpisodeError(
                reason=f"embedding dimension mismatch: {e.actual} != {e.expected}",
                detail="Check embed_dims configuration",
            ) from e

        # Exception mapping: recoverable failures → TransientIngestError
        except (EmbedServiceError, EmbedTimeoutError) as e:
            # Embedding service issues → transient
            raise TransientIngestError(
                message=f"Embedding service unavailable: {e}",
            ) from e
        except (ConnectionError, TimeoutError) as e:
            # Network/connection issues → transient
            raise TransientIngestError(
                message=f"Connection error: {e}",
            ) from e

        # Default-to-transient: any unenumerated exception → transient
        # Losing data is worse than redelivering
        except Exception as e:
            raise TransientIngestError(
                message=f"Unexpected error during ingest: {e}",
            ) from e

    async def _ingest_json(self, episode: MemoryEpisodeV1) -> None:
        """Ingest structured json episode via typed payload registry.

        Algorithm:
        1. Validate payload_type is present
        2. Parse body as JSON
        3. Resolve payload model via registry
        4. Construct and validate typed payload
        5. Write via DeterministicWriter (idempotency layer 1)

        Args:
            episode: Episode with content_format="json"

        Raises:
            PoisonEpisodeError: If payload_type is None
            UnknownPayloadTypeError: If payload_type not in registry
            ValidationError: If payload validation fails
            json.JSONDecodeError: If body is not valid JSON
        """
        # Step 1: Validate payload_type is present
        if episode.payload_type is None:
            raise PoisonEpisodeError(
                reason="missing payload_type for json episode",
                detail="json episodes must specify payload_type",
            )

        # Step 2: Parse body as JSON
        try:
            payload_dict = json.loads(episode.body)
        except json.JSONDecodeError as e:
            raise PoisonEpisodeError(
                reason="unparseable json body",
                detail=str(e),
            ) from e

        # Step 3: Resolve payload model via registry
        payload_model = get_model_for_type(episode.payload_type)

        # Step 4: Construct and validate typed payload
        # ValidationError propagates up to be caught by ingest()
        payload = payload_model(**payload_dict)

        # Step 5: Write via DeterministicWriter
        # DeterministicWriter.write() implements idempotency via content-hash upsert
        await self.writer.write(payload)

    async def _ingest_prose(self, episode: MemoryEpisodeV1) -> None:
        """Ingest markdown/text episode via chunking pipeline.

        Algorithm:
        1. Chunk body via chunk_prose (heading-aware, overlapping)
        2. Write chunks via ChunkWriter (idempotency layer 2: uuid5 keys)

        Empty body → zero chunks → clean return (success, no error).

        Args:
            episode: Episode with content_format="markdown" or "text"
        """
        # Step 1: Chunk prose with settings-driven params
        chunks = chunk_prose(
            episode.body,
            target_tokens=self.settings.chunk_target_tokens,
            overlap_ratio=self.settings.chunk_overlap_ratio,
            source_ref=episode.source_ref,
            project=episode.project_id,
        )

        # Step 2: Write chunks (idempotent via uuid5(episode_id, index))
        # Empty chunks list is allowed and results in no writes
        await self.chunk_writer.write_chunks(episode.episode_id, chunks)
