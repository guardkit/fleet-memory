"""Unit tests for relay schema models.

Tests ContentFormat enum, MemoryEpisodeV1 envelope, and Chunk value object.
Covers all TASK-RLY-001 acceptance criteria.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleet_memory.relay.schema import Chunk, ContentFormat, MemoryEpisodeV1


class TestContentFormat:
    """Test ContentFormat enum defines exactly json, markdown, text (AC-001)."""

    def test_content_format_has_exactly_three_values(self) -> None:
        """ContentFormat enum has exactly json, markdown, and text values."""
        assert len(ContentFormat) == 3
        assert ContentFormat.JSON == "json"
        assert ContentFormat.MARKDOWN == "markdown"
        assert ContentFormat.TEXT == "text"

    def test_content_format_values_are_lowercase(self) -> None:
        """All ContentFormat values are lowercase strings."""
        for fmt in ContentFormat:
            assert fmt.value == fmt.value.lower()
            assert isinstance(fmt.value, str)


class TestMemoryEpisodeV1:
    """Test MemoryEpisodeV1 envelope parsing and validation."""

    def test_parses_valid_json_envelope_without_error(self) -> None:
        """MemoryEpisodeV1 parses structured JSON envelope (AC-002)."""
        envelope = MemoryEpisodeV1(
            episode_id="ep_001",
            project="test_project",
            episode_type="document",
            content_format="json",
            body='{"key": "value"}',
            payload_type="test_payload",
            source_ref="test_source",
        )
        assert envelope.episode_id == "ep_001"
        # constructed with the legacy `project` alias above; canonical attr is project_id
        assert envelope.project_id == "test_project"
        assert envelope.content_format == "json"
        assert envelope.body == '{"key": "value"}'
        assert envelope.payload_type == "test_payload"
        assert envelope.source_ref == "test_source"

    def test_parses_valid_markdown_envelope_without_error(self) -> None:
        """MemoryEpisodeV1 parses markdown envelope (AC-002)."""
        envelope = MemoryEpisodeV1(
            episode_id="ep_002",
            project="test_project",
            episode_type="document",
            content_format="markdown",
            body="# Heading\n\nContent here",
            payload_type=None,
            source_ref=None,
        )
        assert envelope.episode_id == "ep_002"
        assert envelope.content_format == "markdown"
        assert envelope.body == "# Heading\n\nContent here"
        assert envelope.payload_type is None
        assert envelope.source_ref is None

    def test_parses_text_envelope_without_error(self) -> None:
        """MemoryEpisodeV1 parses text envelope."""
        envelope = MemoryEpisodeV1(
            episode_id="ep_003",
            project="test_project",
            episode_type="document",
            content_format="text",
            body="Plain text content",
        )
        assert envelope.episode_id == "ep_003"
        assert envelope.content_format == "text"
        assert envelope.body == "Plain text content"

    def test_content_format_stored_as_is_for_unrecognized_value(self) -> None:
        """Unrecognized content_format like 'yaml' does NOT raise at parse time (AC-003).

        This enables routing/parking logic downstream - the value survives
        parse and becomes a poison decision at the routing layer.
        """
        envelope = MemoryEpisodeV1(
            episode_id="ep_004",
            project="test_project",
            episode_type="document",
            content_format="yaml",  # Unrecognized format
            body="key: value",
        )
        assert envelope.content_format == "yaml"
        assert envelope.episode_id == "ep_004"

    def test_extra_fields_ignored_not_rejected(self) -> None:
        """MemoryEpisodeV1 uses ConfigDict(extra='ignore') for forward compatibility (AC-004)."""
        envelope = MemoryEpisodeV1(
            episode_id="ep_005",
            project="test_project",
            episode_type="document",
            content_format="json",
            body="{}",
            unknown_field="should_be_ignored",
            another_field=42,
        )
        assert envelope.episode_id == "ep_005"
        # Extra fields are silently dropped
        assert not hasattr(envelope, "unknown_field")
        assert not hasattr(envelope, "another_field")

    def test_round_trip_parse_for_json_format(self) -> None:
        """Round-trip parse for JSON format (AC-006)."""
        data = {
            "episode_id": "ep_006",
            "project": "test_project",
            "episode_type": "document",
            "content_format": "json",
            "body": '{"test": true}',
            "payload_type": "test",
            "source_ref": "ref",
        }
        envelope = MemoryEpisodeV1(**data)
        serialized = envelope.model_dump()
        reparsed = MemoryEpisodeV1(**serialized)

        assert reparsed.episode_id == envelope.episode_id
        assert reparsed.content_format == envelope.content_format
        assert reparsed.body == envelope.body

    def test_round_trip_parse_for_markdown_format(self) -> None:
        """Round-trip parse for markdown format (AC-006)."""
        data = {
            "episode_id": "ep_007",
            "project": "test_project",
            "episode_type": "document",
            "content_format": "markdown",
            "body": "# Title\n\nParagraph",
        }
        envelope = MemoryEpisodeV1(**data)
        serialized = envelope.model_dump()
        reparsed = MemoryEpisodeV1(**serialized)

        assert reparsed.episode_id == envelope.episode_id
        assert reparsed.content_format == envelope.content_format
        assert reparsed.body == envelope.body

    def test_round_trip_parse_for_text_format(self) -> None:
        """Round-trip parse for text format (AC-006)."""
        data = {
            "episode_id": "ep_008",
            "project": "test_project",
            "episode_type": "document",
            "content_format": "text",
            "body": "Simple text",
        }
        envelope = MemoryEpisodeV1(**data)
        serialized = envelope.model_dump()
        reparsed = MemoryEpisodeV1(**serialized)

        assert reparsed.episode_id == envelope.episode_id
        assert reparsed.content_format == envelope.content_format
        assert reparsed.body == envelope.body

    def test_round_trip_parse_preserves_extra_field_ignore_behavior(self) -> None:
        """Round-trip with extra fields maintains extra='ignore' behavior (AC-006)."""
        data = {
            "episode_id": "ep_009",
            "project": "test_project",
            "episode_type": "document",
            "content_format": "json",
            "body": "{}",
            "future_field": "value",  # Extra field
        }
        envelope = MemoryEpisodeV1(**data)
        serialized = envelope.model_dump()
        # Extra field not in serialization
        assert "future_field" not in serialized

        # Can reparse and add more extra fields
        serialized["another_extra"] = "ignored"
        reparsed = MemoryEpisodeV1(**serialized)
        assert reparsed.episode_id == "ep_009"
        assert not hasattr(reparsed, "another_extra")

    def test_required_fields_are_enforced(self) -> None:
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryEpisodeV1(
                episode_id="ep_010",
                # Missing project_id, episode_type, content_format, body
            )
        errors = exc_info.value.errors()
        missing_fields = {err["loc"][0] for err in errors if err["type"] == "missing"}
        assert "project_id" in missing_fields
        assert "episode_type" in missing_fields
        assert "content_format" in missing_fields
        assert "body" in missing_fields

    def test_episode_type_required_and_captured(self) -> None:
        """episode_type is required and captured (not dropped by extra='ignore')."""
        envelope = MemoryEpisodeV1(
            episode_id="ep_011",
            project="test_project",
            episode_type="adr",
            content_format="text",
            body="content",
        )
        assert envelope.episode_type == "adr"

    def test_optional_metadata_fields_captured(self) -> None:
        """Optional envelope metadata is captured rather than silently dropped."""
        from datetime import UTC, datetime

        envelope = MemoryEpisodeV1(
            episode_id="ep_012",
            project="test_project",
            episode_type="document",
            content_format="text",
            body="content",
            name="My Episode",
            source="agent-x",
            occurred_at=datetime(2026, 6, 25, tzinfo=UTC),
            published_at=datetime(2026, 6, 25, tzinfo=UTC),
            ingest_hints={"k": "v"},
        )
        assert envelope.name == "My Episode"
        assert envelope.source == "agent-x"
        assert envelope.occurred_at is not None
        assert envelope.published_at is not None
        assert envelope.ingest_hints == {"k": "v"}


class TestChunk:
    """Test Chunk value object immutability and fields (AC-005)."""

    def test_chunk_is_frozen_immutable(self) -> None:
        """Chunk is frozen (immutable) (AC-005)."""
        chunk = Chunk(
            index=0,
            text="Chunk text",
            source_ref="ref",
            project="test_project",
        )
        # Attempting to modify should raise an error
        with pytest.raises(ValidationError) as exc_info:
            chunk.index = 1  # type: ignore[misc]
        assert "frozen" in str(exc_info.value).lower()

    def test_chunk_carries_all_required_fields(self) -> None:
        """Chunk carries index, text, source_ref, project (AC-005)."""
        chunk = Chunk(
            index=42,
            text="Sample chunk text",
            source_ref="source_ref_value",
            project="my_project",
        )
        assert chunk.index == 42
        assert chunk.text == "Sample chunk text"
        assert chunk.source_ref == "source_ref_value"
        assert chunk.project == "my_project"

    def test_chunk_with_none_source_ref(self) -> None:
        """Chunk allows None for source_ref."""
        chunk = Chunk(
            index=0,
            text="Text",
            source_ref=None,
            project="proj",
        )
        assert chunk.source_ref is None
        assert chunk.index == 0

    def test_chunk_validates_required_fields(self) -> None:
        """Chunk enforces required fields."""
        with pytest.raises(ValidationError) as exc_info:
            Chunk(index=0, text="text")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        missing_fields = {err["loc"][0] for err in errors if err["type"] == "missing"}
        assert "project" in missing_fields


class TestImportability:
    """Test that all public types can be imported from module."""

    def test_can_import_all_schema_types(self) -> None:
        """All schema types are importable from fleet_memory.relay.schema."""
        from fleet_memory.relay.schema import Chunk, ContentFormat, MemoryEpisodeV1

        assert ContentFormat is not None
        assert MemoryEpisodeV1 is not None
        assert Chunk is not None
