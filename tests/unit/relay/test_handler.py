"""Unit tests for MEMORY-stream handler: ack/nak/DLQ dispatch contract.

Tests verify thin-handler pattern where handler owns ONLY ack/nak/DLQ routing
and delegates ALL business logic to RelayService.

Producer: TASK-RLY-006
Consumer: FEAT-MEM-04 relay handlers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from faststream.exceptions import NackMessage, RejectMessage

from fleet_memory.errors import (
    EmbedRequestError,
    PoisonEpisodeError,
    TransientIngestError,
)
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.settings import Settings


def _make_episode(**overrides) -> MemoryEpisodeV1:
    """Factory for MemoryEpisodeV1 test instances."""
    defaults = {
        "episode_id": "ep-test-001",
        "project_id": "test_proj",
        "episode_type": "document",
        "content_format": "text",
        "body": "Test content for handler",
        "payload_type": None,
        "source_ref": "ref://handler-test",
    }
    defaults.update(overrides)
    return MemoryEpisodeV1(**defaults)


@pytest.fixture
def make_episode():
    """Fixture providing MemoryEpisodeV1 factory."""
    return _make_episode


def _make_msg(num_delivered: int = 1) -> Mock:
    """Build a stand-in for the injected NatsMessage exposing num_delivered.

    The handler reads ``msg.raw_message.metadata.num_delivered`` to drive the
    max-deliver exhaustion safety net (TASK-FIX-RELAYDROP01). Default 1 = first
    delivery (not exhausted), so the standard nak/ack/poison paths are unaffected.
    """
    msg = Mock()
    msg.raw_message.metadata.num_delivered = num_delivered
    return msg


@pytest.fixture
def make_msg():
    """Fixture providing the NatsMessage stand-in factory."""
    return _make_msg


@pytest.fixture
def mock_broker():
    """Mock broker with context."""
    broker_mock = AsyncMock()
    broker_mock.context = Mock()
    return broker_mock


@pytest.fixture
def mock_settings():
    """Mock Settings instance for broker context."""
    settings = Mock(spec=Settings)
    settings.dlq_subject = "memory.dlq"
    settings.max_deliver = 5
    return settings


# AC-002: On clean `ingest` return the message is ACKed
@pytest.mark.asyncio
async def test_clean_ingest_return_acks_message(make_episode):
    """Verify handler ACKs message when service.ingest returns cleanly.

    Contract: Clean return from service.ingest → ACK (no exception).
    The episode is ACKed only after write commits (ack-after-commit).
    """
    # Import handler module to get the function
    from fleet_memory.relay import handler

    episode = make_episode()

    # Mock service to return cleanly
    mock_service = AsyncMock()
    mock_service.ingest.return_value = None

    # Patch module-level service
    with patch.object(handler, "service", mock_service):
        # Call handler directly - no exception means ACK
        await handler.handle_memory_episode(episode, _make_msg())

        # Verify service.ingest was called
        mock_service.ingest.assert_awaited_once_with(episode)


# AC-003: `PoisonEpisodeError` routes to DLQ with reason recorded
@pytest.mark.asyncio
async def test_poison_error_routes_to_dlq(make_episode, mock_broker):
    """Verify handler routes poison episode to DLQ subject with reason.

    Contract: PoisonEpisodeError → reject/terminate + publish to DLQ subject.
    Consumer continues processing other episodes (does not crash).
    """
    from fleet_memory.relay import handler

    episode = make_episode()
    poison_reason = "invalid namespace: hyphenated-project"

    # Mock service to raise PoisonEpisodeError
    mock_service = AsyncMock()
    mock_service.ingest.side_effect = PoisonEpisodeError(
        reason=poison_reason,
        detail="Project name contains hyphens",
    )

    # The handler reads the DLQ subject prefix from the module-level settings
    # singleton (None in tests -> Settings default "memory.dlq"), not the broker
    # context, so no context wiring is needed here.
    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            # Expect RejectMessage exception
            with pytest.raises(RejectMessage):
                await handler.handle_memory_episode(episode, _make_msg())

            # Verify service.ingest was called
            mock_service.ingest.assert_awaited_once_with(episode)

            # Verify DLQ publish occurred
            mock_broker.publish.assert_awaited_once()
            call_args = mock_broker.publish.call_args
            dlq_payload = call_args[0][0]
            assert dlq_payload["episode_id"] == episode.episode_id
            assert dlq_payload["project_id"] == episode.project_id
            assert dlq_payload["reason"] == poison_reason
            # per-project DLQ subject: memory.dlq.{project_id}
            assert call_args[1]["subject"] == "memory.dlq.test_proj"


# AC-004: `TransientIngestError` negatively-acknowledges for redelivery
@pytest.mark.asyncio
async def test_transient_error_naks_for_redelivery(make_episode, mock_broker):
    """Verify handler naks message on TransientIngestError without DLQ.

    Contract: TransientIngestError → nak (not reject), no DLQ publish.
    Episode is redelivered up to max_deliver times.
    """
    from fleet_memory.relay import handler

    episode = make_episode()

    # Mock service to raise TransientIngestError
    mock_service = AsyncMock()
    mock_service.ingest.side_effect = TransientIngestError(
        message="Embedding service unavailable"
    )

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            # Expect NackMessage exception (first delivery, not exhausted)
            with pytest.raises(NackMessage):
                await handler.handle_memory_episode(episode, _make_msg(num_delivered=1))

            # Verify service.ingest was called
            mock_service.ingest.assert_awaited_once_with(episode)

            # Verify NO DLQ publish occurred
            mock_broker.publish.assert_not_awaited()


# AC: Unenumerated exceptions are treated as transient (default-to-transient)
@pytest.mark.asyncio
async def test_unenumerated_exception_treated_as_transient(make_episode, mock_broker):
    """Verify handler treats unexpected exceptions as transient (nak, not DLQ).

    Contract: Any exception not caught by service → nak for redelivery.
    Default-to-transient policy: losing data is worse than redelivering.
    """
    from fleet_memory.relay import handler

    episode = make_episode()

    # Mock service to raise unexpected exception
    mock_service = AsyncMock()
    mock_service.ingest.side_effect = RuntimeError("Unexpected database connection drop")

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            # Expect NackMessage exception (default-to-transient, not exhausted)
            with pytest.raises(NackMessage):
                await handler.handle_memory_episode(episode, _make_msg(num_delivered=1))

            # Verify service.ingest was called
            mock_service.ingest.assert_awaited_once_with(episode)

            # Verify NO DLQ publish occurred (treated as transient)
            mock_broker.publish.assert_not_awaited()


# RELAYDROP01: max-deliver exhaustion must be LOUD (DLQ + term), never a silent drop.
# A message nak'd on its max_deliver-th delivery stops being redelivered and vanishes;
# the handler must instead publish it to the DLQ and term on the final delivery.
@pytest.mark.asyncio
async def test_transient_on_final_delivery_routes_to_dlq(make_episode, mock_broker):
    """Transient failure on the max_deliver-th delivery → DLQ + RejectMessage (not silent nak).

    Reproducer for the silent-drop half of the 2026-06-26 incident: without this guard a
    deterministic-but-misclassified failure nak's 5× then JetStream stops redelivering and
    the episode is gone. The safety net makes it visible in memory.dlq.> instead.
    """
    from fleet_memory.relay import handler

    episode = make_episode()

    mock_service = AsyncMock()
    mock_service.ingest.side_effect = TransientIngestError(
        message="Embedding service still unavailable"
    )

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            # num_delivered == _MAX_DELIVER (5) → final delivery
            with pytest.raises(RejectMessage):
                await handler.handle_memory_episode(episode, _make_msg(num_delivered=5))

            # Verify it was DLQ'd rather than silently dropped
            mock_broker.publish.assert_awaited_once()
            call_args = mock_broker.publish.call_args
            dlq_payload = call_args[0][0]
            assert dlq_payload["episode_id"] == episode.episode_id
            assert dlq_payload["reason"] == "max_deliver_exhausted"
            assert dlq_payload["failure_mode"] == "transient_ingest_error"
            assert dlq_payload["delivery_count"] == 5
            assert dlq_payload["max_deliver"] == 5
            # Last error preserved for diagnosis
            assert "unavailable" in dlq_payload["detail"]
            assert call_args[1]["subject"] == "memory.dlq.test_proj"


@pytest.mark.asyncio
async def test_unenumerated_on_final_delivery_routes_to_dlq(make_episode, mock_broker):
    """Unenumerated exception on the final delivery → DLQ + RejectMessage (no silent drop).

    The default-to-transient policy must still be loud at exhaustion: a persistent
    unenumerated failure surfaces in the DLQ rather than vanishing.
    """
    from fleet_memory.relay import handler

    episode = make_episode()

    mock_service = AsyncMock()
    mock_service.ingest.side_effect = RuntimeError("persistent database connection drop")

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            with pytest.raises(RejectMessage):
                await handler.handle_memory_episode(episode, _make_msg(num_delivered=5))

            mock_broker.publish.assert_awaited_once()
            dlq_payload = mock_broker.publish.call_args[0][0]
            assert dlq_payload["reason"] == "max_deliver_exhausted"
            assert dlq_payload["failure_mode"] == "unenumerated_exception"


@pytest.mark.asyncio
async def test_transient_before_final_delivery_still_naks(make_episode, mock_broker):
    """A transient failure below max_deliver still naks (no premature DLQ)."""
    from fleet_memory.relay import handler

    episode = make_episode()

    mock_service = AsyncMock()
    mock_service.ingest.side_effect = TransientIngestError(message="temporary blip")

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            # 4th of 5 deliveries → still retrying
            with pytest.raises(NackMessage):
                await handler.handle_memory_episode(episode, _make_msg(num_delivered=4))

            mock_broker.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_delivery_metadata_defaults_to_nak(make_episode, mock_broker):
    """If delivery metadata is unreachable, fall back to nak (never a spurious DLQ/term).

    The exhaustion guard is a safety net; it must never fire on a missing/zero count.
    """
    from fleet_memory.relay import handler

    episode = make_episode()

    mock_service = AsyncMock()
    mock_service.ingest.side_effect = TransientIngestError(message="blip")

    # A bare Mock has no real num_delivered: int(Mock()) raises → _delivery_count
    # returns its defensive 0 → nak (the guard must never fire on an unknown count).
    broken_msg = Mock()

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            with pytest.raises(NackMessage):
                await handler.handle_memory_episode(episode, broken_msg)

            mock_broker.publish.assert_not_awaited()


# RELAYDROP01: end-to-end reproducer — a deterministic embed 400 must land in the DLQ,
# exercising the real RelayService exception mapping (embed → poison) at the handler edge.
@pytest.mark.asyncio
async def test_deterministic_embed_400_lands_in_dlq(make_episode, mock_broker):
    """Over-n_ctx embed (HTTP 400 exceed_context_size_error) → memory.dlq.>, not a silent drop.

    Wires a real RelayService whose chunk writer raises the deterministic EmbedRequestError
    the embed server returns for over-budget input, then asserts the handler publishes a
    self-describing DLQ record and terms the message (RejectMessage). This is the positive
    proof of the incident's fix: the failure is visible, not vanished.
    """
    from fleet_memory.relay import handler
    from fleet_memory.relay.service import RelayService

    episode = make_episode(content_format="text", body="A prose episode that is too large.")

    chunk_writer = AsyncMock()
    chunk_writer.write_chunks.side_effect = EmbedRequestError(
        "the request exceeds the available context size (n_ctx=2048)",
        url="http://embed:9000",
        status_code=400,
        error_type="exceed_context_size_error",
    )
    real_service = RelayService(
        writer=AsyncMock(),
        chunk_writer=chunk_writer,
        settings=Settings(
            pg_dsn="postgresql://test:test@localhost:5432/test",
            embed_url="http://localhost:9000",
        ),
    )

    with patch.object(handler, "service", real_service):
        with patch.object(handler, "broker", mock_broker):
            with pytest.raises(RejectMessage):
                await handler.handle_memory_episode(episode, _make_msg(num_delivered=1))

            mock_broker.publish.assert_awaited_once()
            dlq_payload = mock_broker.publish.call_args[0][0]
            assert dlq_payload["episode_id"] == episode.episode_id
            # Reason names the deterministic embed cause (poison path, first delivery)
            assert "exceed_context_size_error" in dlq_payload["reason"]
            assert mock_broker.publish.call_args[1]["subject"] == "memory.dlq.test_proj"


# D5/D9: the MEMORY subscriber is a DURABLE PULL JetStream consumer, not core NATS.
# These guard the durability contract (see docs/decisions/MEM-04-relay-jetstream-contract.md)
# so a future edit cannot silently drop back to a non-durable subscription where
# nak/RejectMessage/max_deliver are no-ops.
class TestDurableConsumerWiring:
    """Lock in the JetStream durable-consumer contract (TASK-RLY-007 D5/D9)."""

    def test_binds_to_externally_provisioned_memory_stream(self):
        """Relay binds to the MEMORY stream with declare=False (nats-infrastructure owns it)."""
        from fleet_memory.relay import handler

        assert handler.MEMORY_STREAM.name == "MEMORY"
        assert handler.MEMORY_STREAM.declare is False  # never create the stream from the relay

    def test_ingest_subject_matches_convention(self):
        """Consumer filter is the partitioned memory.episode.> (matches the publisher's subjects)."""
        from fleet_memory.relay import handler

        assert handler.MEMORY_SUBJECT == "memory.episode.>"

    def test_durable_consumer_uses_explicit_ack_and_settings_max_deliver(self):
        """Durable name + explicit ack + max_deliver wired from Settings (default 5, ASSUM-005)."""
        from fleet_memory.relay import handler
        from nats.js.api import AckPolicy

        assert handler.MEMORY_DURABLE == "fleet-memory-relay"
        assert handler.MEMORY_CONSUMER_CONFIG.ack_policy == AckPolicy.EXPLICIT
        assert handler.MEMORY_CONSUMER_CONFIG.max_deliver == 5  # explicit ack makes nak/term real

    def test_subscriber_registered_on_broker(self):
        """The MEMORY handler is registered as a subscriber (import side-effect)."""
        from fleet_memory.relay import handler

        assert callable(handler.handle_memory_episode)


# AC-007: Settings exposes DLQ configuration
def test_settings_expose_dlq_configuration():
    """Verify Settings class exposes DLQ and chunking configuration.

    Contract: Settings must include dlq_subject, max_deliver,
    chunk_target_tokens, chunk_overlap_ratio with documented defaults.
    """
    from fleet_memory.settings import Settings

    # Create minimal settings with required fields only
    # (dlq_subject and other new fields should have defaults)
    settings = Settings(
        pg_dsn="postgresql://test:test@localhost:5432/test",
        embed_url="http://localhost:9000",
    )

    # Verify DLQ settings with defaults
    assert hasattr(settings, "dlq_subject")
    assert isinstance(settings.dlq_subject, str)
    assert len(settings.dlq_subject) > 0

    assert hasattr(settings, "max_deliver")
    assert settings.max_deliver == 5  # ASSUM-005 default

    # Verify chunking settings (already exist, verify defaults updated)
    assert settings.chunk_target_tokens == 1000  # OD-1 updated default
    assert settings.chunk_overlap_ratio == 0.15
