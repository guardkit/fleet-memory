"""ChunkWriter: deterministic chunk storage with embed-on-write.

Persists prose chunks under ("fleet_memory", project, "chunk") via AsyncPostgresStore.
Uses uuid5(episode_id, index) for deterministic, idempotent keys.

Producer: TASK-RLY-004
Consumer: FEAT-MEM-04 (relay chunk storage)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fleet_memory.store import validate_namespace
from fleet_memory.writer.identity import FLEET_MEMORY_NAMESPACE

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.relay.schema import Chunk


class ChunkWriter:
    """Deterministic chunk writer with idempotent episode_id-derived keys.

    Implements the key contract: uuid5(episode_id, chunk.index) ensures
    redelivery of the same episode overwrites the same keys in place,
    satisfying the "no duplicate chunks on redelivery" requirement.

    Each stored chunk value includes a 'content' field so the store's
    index config (fields=["content"]) triggers embed-on-write automatically.

    Args:
        store: Configured AsyncPostgresStore with embed-on-write enabled
    """

    def __init__(self, store: AsyncPostgresStore) -> None:
        """Initialize writer with store.

        Args:
            store: AsyncPostgresStore instance (already configured with embedding)
        """
        self.store = store

    async def write_chunks(
        self,
        episode_id: str,
        chunks: list[Chunk],
        episode_meta: dict[str, Any] | None = None,
    ) -> None:
        """Write chunks with deterministic uuid5 keys for idempotent storage.

        Algorithm:
        1. For each chunk, derive namespace from chunk.project
        2. Validate namespace (rejects hyphenated projects)
        3. Compute deterministic key: uuid5(episode_id, chunk.index)
        4. Build stored value with 'content' field for embed-on-write
        5. Write to store (triggers embedding via index config)

        Redelivery of the same (episode_id, chunks) overwrites the same keys,
        ensuring no duplicate chunks (idempotency layer 2).

        Args:
            episode_id: Unique episode identifier (used in key derivation)
            chunks: List of Chunk value objects to persist
            episode_meta: Optional envelope metadata (episode_type + provenance) to
                persist on each chunk record. When provided, episode_type is also
                lifted to a top-level field for queryability.

        Raises:
            NamespaceValidationError: If any chunk's project contains hyphens
                or invalid characters. No writes occur if validation fails.
        """
        if not chunks:
            # Empty list: nothing to write
            return

        # Write each chunk independently
        for chunk in chunks:
            # Step 1: Build namespace from chunk metadata
            namespace = ("fleet_memory", chunk.project, "chunk")

            # Step 2: Validate namespace BEFORE any write
            # This raises NamespaceValidationError for hyphenated projects
            validate_namespace(namespace)

            # Step 3: Compute deterministic key
            # Format: uuid5(episode_id, str(chunk.index))
            # The episode_id is safely embedded in the UUID derivation;
            # path-shaped values cannot escape the namespace tuple
            key_seed = f"{episode_id}:{chunk.index}"
            store_key = str(uuid.uuid5(FLEET_MEMORY_NAMESPACE, key_seed))

            # Step 4: Build stored value with 'content' field
            # The 'content' field is what the store embeds via index config
            stored_value = {
                "content": chunk.text,  # Required for embed-on-write
                "episode_id": episode_id,
                "chunk_index": chunk.index,
                "source_ref": chunk.source_ref,
                "project": chunk.project,
            }

            # Persist envelope metadata so episode_type + provenance are not lost.
            # episode_type is also lifted to a top-level field for queryability.
            if episode_meta is not None:
                stored_value["episode_type"] = episode_meta.get("episode_type")
                stored_value["episode_meta"] = episode_meta

            # Step 5: Write to store (triggers embedding)
            await self.store.aput(namespace, store_key, stored_value)
