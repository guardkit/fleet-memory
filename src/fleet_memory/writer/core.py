"""Deterministic writer core: idempotent content-hash upsert.

Provides DeterministicWriter that transforms typed payloads into AsyncPostgresStore
records with zero language-model calls. Identity comes from TASK-DW-001;
persistence and embed-on-write go through AsyncPostgresStore; input validation
uses the typed payload registry.

Producer: TASK-DW-002
Consumer: FEAT-MEM-03 (deterministic write API)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.registry import PAYLOAD_REGISTRY
from fleet_memory.store import validate_namespace
from fleet_memory.writer.identity import content_hash, record_identity

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.settings import Settings


class DeterministicWriter:
    """Deterministic writer with idempotent content-hash upsert.

    Transforms typed payloads into AsyncPostgresStore records with no LLM calls.
    Implements version-aware upsert: no-op for identical content, version++ for changes.

    Args:
        store: Configured AsyncPostgresStore with embed-on-write enabled
        settings: Configuration (used for validation and metadata)
    """

    def __init__(self, store: AsyncPostgresStore, settings: Settings) -> None:
        """Initialize writer with store and settings.

        Args:
            store: AsyncPostgresStore instance (already configured with embedding)
            settings: Settings instance for validation
        """
        self.store = store
        self.settings = settings

    async def write(self, payload: BasePayload) -> None:
        """Write a single typed payload with idempotent content-hash upsert.

        Algorithm:
        1. Validate payload is registered
        2. Build and validate namespace
        3. Compute identity and content_hash
        4. Check for existing record
        5. Apply upsert logic (no-op if same hash, version++ if different)

        Args:
            payload: A registered BasePayload subclass instance

        Raises:
            ValueError: If payload type is not registered
            NamespaceValidationError: If namespace contains invalid identifiers
            RuntimeError: If embedding service unavailable or database unreachable
        """
        # Step 1: Validate payload is registered
        payload_type = payload.payload_type
        if payload_type not in PAYLOAD_REGISTRY:
            raise ValueError(
                f"Payload type '{payload_type}' is not a recognized payload type. "
                f"Only registered BasePayload subclasses can be written."
            )

        # Step 2: Build namespace and validate before any store operation
        namespace = ("fleet_memory", payload.project, payload_type)
        validate_namespace(namespace)

        # Step 3: Compute identity and new content hash
        natural_key = payload.natural_key
        identity = record_identity(natural_key)
        new_hash = content_hash(payload)

        # Step 4: Read any existing record for this key
        store_key = str(identity)
        existing = await self.store.aget(namespace, store_key)

        # Step 5: Apply upsert logic
        if existing is None:
            # No existing record - write new at version 1
            version = 1
            await self._write_record(namespace, store_key, payload, new_hash, version)
        else:
            # Existing record - check content hash
            existing_value = existing.value
            existing_hash = existing_value.get("content_hash")

            if existing_hash == new_hash:
                # Same content hash - no-op (ASSUM-004)
                # Do NOT re-embed or update timestamps
                return
            else:
                # Different content hash - versioned update (ASSUM-005)
                existing_version = existing_value.get("version", 1)
                new_version = existing_version + 1
                await self._write_record(namespace, store_key, payload, new_hash, new_version)

    async def write_batch(self, payloads: list[BasePayload]) -> None:
        """Write a batch of payloads with within-batch duplicate key collapsing.

        Produces exactly one record per distinct natural key. Within-batch duplicates
        for the same key collapse to the last occurrence.

        Args:
            payloads: List of typed payload instances

        Raises:
            ValueError: If any payload type is not registered
            NamespaceValidationError: If any namespace is invalid
        """
        if not payloads:
            return

        # Collapse duplicates: last occurrence wins for each natural key
        seen_keys: dict[str, BasePayload] = {}
        for payload in payloads:
            natural_key = payload.natural_key
            seen_keys[natural_key] = payload

        # Write each unique payload
        for payload in seen_keys.values():
            await self.write(payload)

    async def _write_record(
        self,
        namespace: tuple[str, ...],
        store_key: str,
        payload: BasePayload,
        content_hash_value: str,
        version: int,
    ) -> None:
        """Write a record to the store with content field for embedding.

        Args:
            namespace: The namespace tuple
            store_key: The store key (stringified UUID)
            payload: The payload to write
            content_hash_value: Pre-computed content hash
            version: The version number to store
        """
        # Serialize payload to create content string
        # The content field is what gets embedded by the store
        payload_dict = payload.model_dump()

        # Create content as canonical JSON for embedding
        # This is what the embedding index will process
        content_json = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))

        # Build the stored value with required "content" field
        # The store's index config (fields=["content"]) will embed this field
        stored_value = {
            "content": content_json,  # Required for embed-on-write
            "content_hash": content_hash_value,
            "version": version,
            "payload_type": payload.payload_type,
            "natural_key": payload.natural_key,
            "project": payload.project,
            "identifier": payload.identifier,
        }

        # Write to store (triggers embedding via index config)
        await self.store.aput(namespace, store_key, stored_value)
