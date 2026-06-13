"""Pydantic message schemas for relay stream processing.

Defines the inbound MemoryEpisodeV1 envelope, ContentFormat enum, and Chunk
value object consumed by downstream relay tasks.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


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

    model_config = ConfigDict(extra="ignore")  # Forward compatibility

    episode_id: str
    project: str
    content_format: str  # Raw string, NOT validated against ContentFormat enum
    body: str
    payload_type: str | None = None
    source_ref: str | None = None


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
