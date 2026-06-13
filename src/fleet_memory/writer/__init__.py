"""Writer module: deterministic payload-to-store writer with idempotent upsert.

Exports:
    DeterministicWriter: Main writer class with content-hash upsert logic
    record_identity: Generate stable UUIDv5 from natural key
    content_hash: Generate deterministic hash over payload content
"""

from fleet_memory.writer.core import DeterministicWriter
from fleet_memory.writer.identity import content_hash, record_identity

__all__ = ["DeterministicWriter", "record_identity", "content_hash"]
