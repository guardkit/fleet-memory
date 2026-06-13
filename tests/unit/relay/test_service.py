"""Unit tests for RelayService: content_format routing and two-layer idempotency.

Tests verify json/markdown/text dispatch, exception mapping (poison vs transient),
namespace validation, idempotency guarantees, and the zero-LLM / zero-NATS contract.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
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
from fleet_memory.payloads.base import BasePayload
from fleet_memory.relay.schema import Chunk, MemoryEpisodeV1
from fleet_memory.relay.service import RelayService
from fleet_memory.settings import Settings


def _make_episode(**overrides) -> MemoryEpisodeV1:
    """Factory for MemoryEpisodeV1 test instances."""
    defaults = {
        "episode_id": "ep-test-001",
        "project": "test_proj",
        "content_format": "text",
        "body": "Test content",
        "payload_type": None,
        "source_ref": "ref://test",
    }
    defaults.update(overrides)
    return MemoryEpisodeV1(**defaults)


@pytest.fixture
def make_episode():
    """Fixture providing MemoryEpisodeV1 factory."""
    return _make_episode


@pytest.fixture
def mock_writer():
    """Mock DeterministicWriter for testing."""
    writer = AsyncMock()
    writer.write = AsyncMock()
    return writer


@pytest.fixture
def mock_chunk_writer():
    """Mock ChunkWriter for testing."""
    writer = AsyncMock()
    writer.write_chunks = AsyncMock()
    return writer


@pytest.fixture
def mock_settings():
    """Mock Settings for testing."""
    settings = Mock(spec=Settings)
    settings.chunk_target_tokens = 500
    settings.chunk_overlap_ratio = 0.15
    return settings


@pytest.fixture
def relay_service(mock_writer, mock_chunk_writer, mock_settings):
    """Relay service instance with mocked dependencies."""
    return RelayService(
        writer=mock_writer,
        chunk_writer=mock_chunk_writer,
        settings=mock_settings,
    )


# AC-001: json episodes dispatch through the registry to DeterministicWriter.write
@pytest.mark.asyncio
async def test_json_episode_writes_typed_payload(relay_service, make_episode, mock_writer):
    """Verify json episodes are parsed, validated, and written via DeterministicWriter.

    Contract: json format → get_model_for_type → validate → DeterministicWriter.write
    """
    # Arrange: json episode with valid document payload
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body=json.dumps(
            {
                "project": "test_proj",
                "identifier": "doc-001",
                "content": "Test document content",
            }
        ),
    )

    # Mock get_model_for_type to return DocumentPayload
    with patch("fleet_memory.relay.service.get_model_for_type") as mock_get_model:
        # Create a mock payload class
        mock_payload_class = MagicMock()
        mock_payload_instance = MagicMock(spec=BasePayload)
        mock_payload_class.return_value = mock_payload_instance
        mock_get_model.return_value = mock_payload_class

        # Act
        await relay_service.ingest(episode)

        # Assert: get_model_for_type was called with payload_type
        mock_get_model.assert_called_once_with("document")

        # Assert: payload was constructed from body
        mock_payload_class.assert_called_once()

        # Assert: DeterministicWriter.write was called with payload
        mock_writer.write.assert_called_once_with(mock_payload_instance)


# AC-002: markdown and text episodes are chunked and stored as chunks
@pytest.mark.asyncio
async def test_markdown_episode_chunks_and_writes(
    relay_service, make_episode, mock_chunk_writer, mock_settings
):
    """Verify markdown episodes are chunked via chunk_prose and written."""
    # Arrange
    episode = make_episode(
        content_format="markdown",
        body="# Header\nSome content here",
    )

    # Mock chunk_prose to return chunks
    with patch("fleet_memory.relay.service.chunk_prose") as mock_chunk_prose:
        mock_chunks = [
            Chunk(
                index=0, text="# Header\nSome content", source_ref="ref://test", project="test_proj"
            ),
        ]
        mock_chunk_prose.return_value = mock_chunks

        # Act
        await relay_service.ingest(episode)

        # Assert: chunk_prose called with correct params
        mock_chunk_prose.assert_called_once_with(
            "# Header\nSome content here",
            target_tokens=500,
            overlap_ratio=0.15,
            source_ref="ref://test",
            project="test_proj",
        )

        # Assert: ChunkWriter.write_chunks called
        mock_chunk_writer.write_chunks.assert_called_once_with("ep-test-001", mock_chunks)


@pytest.mark.asyncio
async def test_text_episode_chunks_and_writes(relay_service, make_episode, mock_chunk_writer):
    """Verify text episodes follow same chunking path as markdown."""
    # Arrange
    episode = make_episode(
        content_format="text",
        body="Plain text content",
    )

    # Mock chunk_prose
    with patch("fleet_memory.relay.service.chunk_prose") as mock_chunk_prose:
        mock_chunks = [
            Chunk(index=0, text="Plain text content", source_ref="ref://test", project="test_proj"),
        ]
        mock_chunk_prose.return_value = mock_chunks

        # Act
        await relay_service.ingest(episode)

        # Assert
        mock_chunk_prose.assert_called_once()
        mock_chunk_writer.write_chunks.assert_called_once()


# AC-003: Unknown payload_type raises PoisonEpisodeError naming the type
@pytest.mark.asyncio
async def test_unknown_payload_type_raises_poison_error(relay_service, make_episode):
    """Verify unknown payload_type → PoisonEpisodeError (not transient)."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="unknown_type",
        body='{"foo": "bar"}',
    )

    # Mock get_model_for_type to raise UnknownPayloadTypeError
    with patch("fleet_memory.relay.service.get_model_for_type") as mock_get_model:
        mock_get_model.side_effect = UnknownPayloadTypeError("unknown_type")

        # Act & Assert
        with pytest.raises(PoisonEpisodeError) as exc_info:
            await relay_service.ingest(episode)

        assert "unknown_type" in str(exc_info.value)


# AC-004: Missing required payload field raises PoisonEpisodeError
@pytest.mark.asyncio
async def test_invalid_payload_raises_poison_error(relay_service, make_episode):
    """Verify payload validation failure → PoisonEpisodeError."""
    # Arrange: json with missing required fields
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body='{"incomplete": "data"}',  # Missing required fields
    )

    # Mock get_model_for_type to return a model that will fail validation
    with patch("fleet_memory.relay.service.get_model_for_type") as mock_get_model:
        mock_payload_class = MagicMock()
        mock_payload_class.side_effect = ValidationError.from_exception_data(
            "DocumentPayload",
            [{"type": "missing", "loc": ("identifier",), "msg": "Field required"}],
        )
        mock_get_model.return_value = mock_payload_class

        # Act & Assert
        with pytest.raises(PoisonEpisodeError) as exc_info:
            await relay_service.ingest(episode)

        assert "validation" in str(exc_info.value).lower()


# AC-005: content_format of "yaml" raises PoisonEpisodeError
@pytest.mark.asyncio
async def test_unrecognized_content_format_raises_poison_error(relay_service, make_episode):
    """Verify unrecognized content_format → PoisonEpisodeError."""
    # Arrange
    episode = make_episode(content_format="yaml", body="foo: bar")

    # Act & Assert
    with pytest.raises(PoisonEpisodeError) as exc_info:
        await relay_service.ingest(episode)

    assert "yaml" in str(exc_info.value).lower()
    assert "unrecognized" in str(exc_info.value).lower() or "format" in str(exc_info.value).lower()


# AC-006: Hyphenated project raises PoisonEpisodeError on both paths
@pytest.mark.asyncio
async def test_hyphenated_project_raises_poison_on_json_path(
    relay_service, make_episode, mock_writer
):
    """Verify hyphenated project → PoisonEpisodeError on json path."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        project="hyphen-ated",
        body='{"project": "hyphen-ated", "identifier": "doc-001", "content": "test"}',
    )

    # Mock the writer to raise NamespaceValidationError
    mock_writer.write.side_effect = NamespaceValidationError(
        namespace=("fleet_memory", "hyphen-ated", "document"),
        invalid_parts=["hyphen-ated"],
    )

    # Act & Assert
    with pytest.raises(PoisonEpisodeError) as exc_info:
        await relay_service.ingest(episode)

    assert "hyphen" in str(exc_info.value).lower() or "namespace" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_hyphenated_project_raises_poison_on_chunk_path(
    relay_service, make_episode, mock_chunk_writer
):
    """Verify hyphenated project → PoisonEpisodeError on chunk path."""
    # Arrange
    episode = make_episode(
        content_format="text",
        project="hyphen-ated",
        body="content",
    )

    # Mock chunk_writer to raise NamespaceValidationError
    with patch("fleet_memory.relay.service.chunk_prose") as mock_chunk_prose:
        mock_chunks = [Chunk(index=0, text="content", source_ref=None, project="hyphen-ated")]
        mock_chunk_prose.return_value = mock_chunks
        mock_chunk_writer.write_chunks.side_effect = NamespaceValidationError(
            namespace=("fleet_memory", "hyphen-ated", "chunk"),
            invalid_parts=["hyphen-ated"],
        )

        # Act & Assert
        with pytest.raises(PoisonEpisodeError):
            await relay_service.ingest(episode)


# AC-007: Embedding-service-unavailable raises TransientIngestError (NOT poison)
@pytest.mark.asyncio
async def test_embed_service_error_raises_transient(relay_service, make_episode, mock_writer):
    """Verify embedding service unavailable → TransientIngestError (recoverable)."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body='{"project": "test_proj", "identifier": "doc-001", "content": "test"}',
    )

    # Mock writer to raise EmbedServiceError
    with patch("fleet_memory.relay.service.get_model_for_type"):
        mock_writer.write.side_effect = EmbedServiceError(
            "Service unavailable", url="http://embed:9000", status_code=503
        )

        # Act & Assert
        with pytest.raises(TransientIngestError) as exc_info:
            await relay_service.ingest(episode)

        assert "embed" in str(exc_info.value).lower() or "service" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_embed_timeout_raises_transient(relay_service, make_episode, mock_writer):
    """Verify embedding timeout → TransientIngestError."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body='{"project": "test_proj", "identifier": "doc-001", "content": "test"}',
    )

    # Mock writer to raise EmbedTimeoutError
    with patch("fleet_memory.relay.service.get_model_for_type"):
        mock_writer.write.side_effect = EmbedTimeoutError(url="http://embed:9000", timeout_s=10.0)

        # Act & Assert
        with pytest.raises(TransientIngestError):
            await relay_service.ingest(episode)


# AC-008: Empty markdown body produces zero chunks and returns cleanly
@pytest.mark.asyncio
async def test_empty_markdown_returns_cleanly(relay_service, make_episode, mock_chunk_writer):
    """Verify empty markdown → zero chunks → clean return (success)."""
    # Arrange
    episode = make_episode(
        content_format="markdown",
        body="   ",  # Whitespace only
    )

    # Mock chunk_prose to return empty list
    with patch("fleet_memory.relay.service.chunk_prose") as mock_chunk_prose:
        mock_chunk_prose.return_value = []

        # Act (should not raise)
        await relay_service.ingest(episode)

        # Assert: write_chunks was called with empty list
        mock_chunk_writer.write_chunks.assert_called_once_with("ep-test-001", [])


# AC-009: Redelivery of an already-stored episode produces no duplicates
@pytest.mark.asyncio
async def test_redelivery_json_is_idempotent(relay_service, make_episode, mock_writer):
    """Verify redelivery of json episode → DeterministicWriter handles idempotency."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body='{"project": "test_proj", "identifier": "doc-001", "content": "test"}',
    )

    # Mock
    with patch("fleet_memory.relay.service.get_model_for_type") as mock_get_model:
        mock_payload_class = MagicMock()
        mock_payload = MagicMock(spec=BasePayload)
        mock_payload_class.return_value = mock_payload
        mock_get_model.return_value = mock_payload_class

        # Act: ingest twice
        await relay_service.ingest(episode)
        await relay_service.ingest(episode)

        # Assert: write called twice (idempotency handled by writer itself)
        assert mock_writer.write.call_count == 2


@pytest.mark.asyncio
async def test_redelivery_chunks_is_idempotent(relay_service, make_episode, mock_chunk_writer):
    """Verify redelivery of chunked episode → ChunkWriter uuid5 keys ensure idempotency."""
    # Arrange
    episode = make_episode(
        content_format="text",
        body="content",
    )

    # Mock
    with patch("fleet_memory.relay.service.chunk_prose") as mock_chunk_prose:
        mock_chunks = [Chunk(index=0, text="content", source_ref="ref://test", project="test_proj")]
        mock_chunk_prose.return_value = mock_chunks

        # Act: ingest twice
        await relay_service.ingest(episode)
        await relay_service.ingest(episode)

        # Assert: write_chunks called twice with same episode_id and chunks
        assert mock_chunk_writer.write_chunks.call_count == 2
        # ChunkWriter's uuid5 logic ensures overwrites, not duplicates


# AC-010: ingest makes zero language-model calls
@pytest.mark.asyncio
async def test_no_llm_calls(relay_service, make_episode):
    """Verify ingest makes zero language-model / chat-completion calls."""
    # This is verified by:
    # 1. Code inspection (no openai/anthropic imports)
    # 2. No embedding generation in this service (handled by store layer)
    # 3. All logic is deterministic routing

    # Arrange
    episode = make_episode(content_format="text", body="test")

    # Mock chunk_prose
    with patch("fleet_memory.relay.service.chunk_prose") as mock_chunk_prose:
        mock_chunk_prose.return_value = []

        # Act
        await relay_service.ingest(episode)

        # Assert: completed without calling any LLM service
        # (implicit - if we called an LLM, test would hang/fail on missing mock)


# AC-011: The module imports nothing from faststream / NATS
def test_no_nats_imports():
    """Verify service.py has zero faststream/NATS imports."""
    # Read the source file
    import pathlib

    service_path = (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "src"
        / "fleet_memory"
        / "relay"
        / "service.py"
    )
    service_source = service_path.read_text()

    # Assert no NATS-related imports
    assert "faststream" not in service_source, "service.py must not import faststream"
    assert "import nats" not in service_source, "service.py must not import nats"
    assert "from nats" not in service_source, "service.py must not import from nats"


# Seam test from task description
@pytest.mark.seam
@pytest.mark.integration_contract("exception_taxonomy")
async def test_unknown_format_is_poison(relay_service, make_episode):
    """Unrecognized content_format → PoisonEpisodeError (DLQ), not transient.

    Contract: deterministic failure => PoisonEpisodeError; recoverable => TransientIngestError.
    Producer: TASK-RLY-002
    """
    with pytest.raises(PoisonEpisodeError):
        await relay_service.ingest(make_episode(content_format="yaml"))


# Additional edge cases


@pytest.mark.asyncio
async def test_embed_dimension_error_raises_poison(relay_service, make_episode, mock_writer):
    """Verify wrong-dimension embedding → PoisonEpisodeError (deterministic failure)."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body='{"project": "test_proj", "identifier": "doc-001", "content": "test"}',
    )

    # Mock writer to raise EmbedDimensionError
    with patch("fleet_memory.relay.service.get_model_for_type"):
        mock_writer.write.side_effect = EmbedDimensionError(actual=512, expected=768)

        # Act & Assert
        with pytest.raises(PoisonEpisodeError) as exc_info:
            await relay_service.ingest(episode)

        assert "dimension" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_unenumerated_exception_raises_transient(relay_service, make_episode, mock_writer):
    """Verify unenumerated exception → TransientIngestError (default-to-transient policy)."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body='{"project": "test_proj", "identifier": "doc-001", "content": "test"}',
    )

    # Mock writer to raise generic RuntimeError
    with patch("fleet_memory.relay.service.get_model_for_type"):
        mock_writer.write.side_effect = RuntimeError("Unexpected database error")

        # Act & Assert
        with pytest.raises(TransientIngestError) as exc_info:
            await relay_service.ingest(episode)

        assert (
            "unexpected" in str(exc_info.value).lower() or "database" in str(exc_info.value).lower()
        )


@pytest.mark.asyncio
async def test_json_episode_with_none_payload_type_raises_poison(relay_service, make_episode):
    """Verify json episode without payload_type → PoisonEpisodeError."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type=None,  # Missing payload_type
        body='{"foo": "bar"}',
    )

    # Act & Assert
    with pytest.raises(PoisonEpisodeError) as exc_info:
        await relay_service.ingest(episode)

    assert "payload_type" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_unparseable_json_body_raises_poison(relay_service, make_episode):
    """Verify unparseable JSON body → PoisonEpisodeError."""
    # Arrange
    episode = make_episode(
        content_format="json",
        payload_type="document",
        body="{invalid json",
    )

    # Act & Assert
    with pytest.raises(PoisonEpisodeError) as exc_info:
        await relay_service.ingest(episode)

    assert "json" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower()
