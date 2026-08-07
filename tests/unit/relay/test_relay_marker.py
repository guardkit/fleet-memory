"""The relay records its own progress — and never lets that recording cost a message.

The relay's only proof of life is this marker: a clean ingest logs nothing at all, so
without it a working relay and a dead one look identical from outside. That is exactly
how the memory flywheel went dark for a month.

The invariant these tests defend: **recording is a courtesy, acking is the contract.**
A marker that explodes must not change a single routing decision.

Same fakes as the DLQ-invariant component test: real handler, real RelayService
classification, AsyncMock broker, no NATS, no Postgres.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from faststream.exceptions import NackMessage, RejectMessage

from fleet_memory.errors import EmbedRequestError, TransientIngestError
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.relay.service import RelayService
from fleet_memory.settings import Settings


def _episode(episode_id: str = "ep-1", project_id: str = "guardkit") -> MemoryEpisodeV1:
    return MemoryEpisodeV1(
        episode_id=episode_id,
        project_id=project_id,
        episode_type="document",
        content_format="text",
        body=f"Prose body for {episode_id}.",
        payload_type=None,
        source_ref=f"ref://{episode_id}",
    )


def _msg(num_delivered: int = 1) -> Mock:
    msg = Mock()
    msg.raw_message.metadata.num_delivered = num_delivered
    return msg


class _RecordingMarker:
    """Stands in for RelayMarker; records the calls the handler makes."""

    def __init__(self) -> None:
        self.ingests = 0
        self.messages: list[str] = []

    def record_ingest(self) -> None:
        self.ingests += 1

    def record_message(self, *, disposition: str) -> None:
        self.messages.append(disposition)


class _ExplodingMarker:
    """A marker whose every write fails — e.g. a full disk or a read-only mount."""

    def record_ingest(self) -> None:
        raise OSError("no space left on device")

    def record_message(self, *, disposition: str) -> None:
        raise OSError("no space left on device")


class _PoisoningChunkWriter:
    """Fake ChunkWriter that 400s the ids it is told to, as the embed server does."""

    def __init__(self, poison_ids: set[str] | None = None) -> None:
        self.poison_ids = poison_ids or set()
        self.stored_ids: list[str] = []

    async def write_chunks(self, episode_id, chunks, episode_meta=None) -> None:
        if episode_id in self.poison_ids:
            raise EmbedRequestError(
                "the request exceeds the available context size (n_ctx=2048)",
                url="http://embed:9000",
                status_code=400,
                error_type="exceed_context_size_error",
            )
        self.stored_ids.append(episode_id)


def _service(chunk_writer) -> RelayService:
    settings = Mock(spec=Settings)
    settings.chunk_target_tokens = 1000
    settings.chunk_overlap_ratio = 0.15
    return RelayService(writer=AsyncMock(), chunk_writer=chunk_writer, settings=settings)


@pytest.mark.asyncio
async def test_a_successful_ingest_is_recorded():
    from fleet_memory.relay import handler

    chunk_writer = _PoisoningChunkWriter()
    marker = _RecordingMarker()

    with patch.object(handler, "service", _service(chunk_writer)):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", marker):
                await handler.handle_memory_episode(_episode(), _msg())

    assert marker.ingests == 1
    assert marker.messages == []
    assert chunk_writer.stored_ids == ["ep-1"]


@pytest.mark.asyncio
async def test_a_poison_episode_records_a_dlq_message_and_still_rejects():
    from fleet_memory.relay import handler

    chunk_writer = _PoisoningChunkWriter(poison_ids={"ep-poison"})
    marker = _RecordingMarker()

    with patch.object(handler, "service", _service(chunk_writer)):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", marker):
                with pytest.raises(RejectMessage):
                    await handler.handle_memory_episode(_episode("ep-poison"), _msg())

    assert marker.ingests == 0
    assert marker.messages == ["dlq"]


@pytest.mark.asyncio
async def test_a_transient_failure_records_a_nak_and_still_naks():
    from fleet_memory.relay import handler

    service = AsyncMock()
    service.ingest.side_effect = TransientIngestError("embed service unreachable")
    marker = _RecordingMarker()

    with patch.object(handler, "service", service):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", marker):
                with pytest.raises(NackMessage):
                    await handler.handle_memory_episode(_episode(), _msg())

    assert marker.ingests == 0
    assert marker.messages == ["nak"]


@pytest.mark.asyncio
async def test_max_deliver_exhaustion_records_a_dlq_message():
    from fleet_memory.relay import handler

    service = AsyncMock()
    service.ingest.side_effect = TransientIngestError("still unreachable")
    marker = _RecordingMarker()

    with patch.object(handler, "service", service):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", marker):
                with pytest.raises(RejectMessage):
                    await handler.handle_memory_episode(_episode(), _msg(num_delivered=5))

    assert marker.messages == ["dlq"]


@pytest.mark.asyncio
async def test_a_marker_that_raises_does_not_prevent_the_ack_or_propagate():
    """The whole point: recording progress can never cost a message."""
    from fleet_memory.relay import handler

    chunk_writer = _PoisoningChunkWriter()

    with patch.object(handler, "service", _service(chunk_writer)):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", _ExplodingMarker()):
                # No exception escapes -> FastStream acks the message.
                await handler.handle_memory_episode(_episode(), _msg())

    assert chunk_writer.stored_ids == ["ep-1"]


@pytest.mark.asyncio
async def test_a_marker_that_raises_does_not_change_the_poison_routing():
    from fleet_memory.relay import handler

    chunk_writer = _PoisoningChunkWriter(poison_ids={"ep-poison"})
    broker = AsyncMock()

    with patch.object(handler, "service", _service(chunk_writer)):
        with patch.object(handler, "broker", broker):
            with patch.object(handler, "marker", _ExplodingMarker()):
                with pytest.raises(RejectMessage):
                    await handler.handle_memory_episode(_episode("ep-poison"), _msg())

    subjects = [c.kwargs.get("subject", "") for c in broker.publish.call_args_list]
    assert any(s.startswith("memory.dlq.") for s in subjects)


@pytest.mark.asyncio
async def test_no_marker_is_a_no_op_which_is_how_every_test_env_runs():
    from fleet_memory.relay import handler

    chunk_writer = _PoisoningChunkWriter()

    with patch.object(handler, "service", _service(chunk_writer)):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", None):
                await handler.handle_memory_episode(_episode(), _msg())

    assert chunk_writer.stored_ids == ["ep-1"]


def test_the_handler_module_exposes_a_marker_slot_defaulting_to_none():
    from fleet_memory.relay import handler

    assert hasattr(handler, "marker")


@pytest.mark.asyncio
async def test_a_real_relay_marker_writes_a_file_the_fence_can_read(tmp_path):
    """End-to-end across the seam: the handler's write, the fence's read."""
    from fleet_memory.fence.marker import RelayMarker, read_marker
    from fleet_memory.relay import handler

    path = tmp_path / "state" / "relay-progress.json"
    real_marker = RelayMarker(path)
    real_marker.record_start()
    chunk_writer = _PoisoningChunkWriter()

    with patch.object(handler, "service", _service(chunk_writer)):
        with patch.object(handler, "broker", AsyncMock()):
            with patch.object(handler, "marker", real_marker):
                await handler.handle_memory_episode(_episode(), _msg())

    state = read_marker(path).state
    assert state is not None
    assert state.ingests_since_start == 1
    assert state.last_ingest_at is not None
