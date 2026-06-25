"""Pydantic message schemas for relay stream processing.

Defines the inbound MemoryEpisodeV1 envelope, ContentFormat enum, and Chunk
value object consumed by downstream relay tasks.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ContentFormat(str, Enum):
    """Recognized content formats for memory episodes.

    Only these three formats are recognized by the chunker.
    Unrecognized formats are parked at routing time (negative scenario).
    """

    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"


class MemoryEpisodeV1(BaseModel):
    """Inbound envelope published by nats-core onto the MEMORY stream.

    This is the producer-side contract for memory episodes.
    The content_format field is stored as-is (raw string) to allow
    unrecognized values to survive parse and be routed/parked downstream.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)  # Forward compatibility

    episode_id: str
    # Canonical contract field is project_id (nats-core MemoryEpisodeV1, published on
    # the subject partition). "project" is accepted as a transitional alias so legacy
    # producers/tests keep working; it maps to the storage namespace's project segment
    # at the relay boundary (service/chunk_writer keep the internal name `project`).
    project_id: str = Field(validation_alias=AliasChoices("project_id", "project"))
    # Coarse source category (adr/feature_outcome/review_report/document/...). REQUIRED:
    # the publisher (nats-core MemoryEpisodeV1) always sends it and the relay must capture
    # + persist it rather than silently dropping it via extra="ignore". Kept as a raw
    # string (no pattern) — the publisher already enforces the NATS-safe identifier shape.
    episode_type: str
    content_format: str  # Raw string, NOT validated against ContentFormat enum
    body: str
    payload_type: str | None = None
    source_ref: str | None = None
    # Optional envelope metadata carried by the publisher. Captured here (instead of being
    # dropped by extra="ignore") and persisted alongside content via the writers so it is
    # not silently lost at ingestion.
    name: str | None = None
    source: str | None = None
    occurred_at: datetime | None = None
    published_at: datetime | None = None
    ingest_hints: dict[str, Any] | None = None


class Chunk(BaseModel):
    """Frozen value object produced by chunker and consumed by chunk writer.

    Represents a single chunk of text extracted from a memory episode.
    No storage logic — pure data transfer object.
    """

    model_config = ConfigDict(frozen=True)  # Immutable

    index: int
    text: str
    source_ref: str | None
    project: str
