"""Record identity and content-hash helpers.

Provides two pure, I/O-free derivations for deterministic record writes:

- record_identity: Stable UUIDv5 from natural key
- content_hash: Deterministic hash over semantic content (excludes version)

Both functions are pure with zero dependencies on settings, store, or LLM.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleet_memory.payloads.base import BasePayload

# Single application-wide namespace UUID for record identity generation (ASSUM-002)
# This constant ensures the same natural key always produces the same UUID
# across all processes and runs
FLEET_MEMORY_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def record_identity(natural_key: str) -> uuid.UUID:
    """Generate deterministic UUIDv5 from natural key.

    The same natural key always produces the same UUID across all processes
    and runs, using the single application-wide namespace constant.

    Args:
        natural_key: Three-segment colon-separated key (<type>:<project>:<id>)

    Returns:
        UUIDv5 derived from natural_key using FLEET_MEMORY_NAMESPACE

    Examples:
        >>> key = "adr:my_project:ADR_001"
        >>> uuid1 = record_identity(key)
        >>> uuid2 = record_identity(key)
        >>> uuid1 == uuid2  # Always true - deterministic
        True
        >>> uuid1.version == 5  # UUIDv5
        True
    """
    return uuid.uuid5(FLEET_MEMORY_NAMESPACE, natural_key)


def content_hash(payload: BasePayload) -> str:
    """Generate stable hash over payload's semantic content.

    Excludes version and any write-time metadata so an unchanged re-write
    hashes identically. Uses canonical JSON serialization (sorted keys) to
    ensure dict ordering never changes the hash.

    Args:
        payload: BasePayload instance with semantic content

    Returns:
        Hex-encoded SHA-256 hash of canonical semantic content

    Examples:
        >>> from fleet_memory.payloads.base import BasePayload
        >>> p1 = BasePayload(
        ...     project="test", identifier="id1", source_ref="src", version=1
        ... )
        >>> p2 = BasePayload(
        ...     project="test", identifier="id1", source_ref="src", version=2
        ... )
        >>> content_hash(p1) == content_hash(p2)  # Version excluded
        True
    """
    # Get full payload as dict
    payload_dict = payload.model_dump()

    # Remove version (write-time metadata) to get semantic content only
    # This ensures an unchanged re-write hashes identically (ASSUM-003)
    semantic_content = {k: v for k, v in payload_dict.items() if k != "version"}

    # Canonicalize to JSON with sorted keys to ensure deterministic serialization
    # This prevents dict ordering from changing the hash
    canonical_json = json.dumps(
        semantic_content,
        sort_keys=True,
        separators=(",", ":"),  # No spaces for minimal representation
    )

    # Hash the canonical representation
    hash_bytes = hashlib.sha256(canonical_json.encode("utf-8")).digest()

    # Return hex-encoded hash
    return hash_bytes.hex()
