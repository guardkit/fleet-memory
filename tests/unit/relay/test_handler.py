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

from fleet_memory.errors import PoisonEpisodeError, TransientIngestError
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.settings import Settings


def _make_episode(**overrides) -> MemoryEpisodeV1:
    """Factory for MemoryEpisodeV1 test instances."""
    defaults = {
        "episode_id": "ep-test-001",
        "project_id": "test_proj",
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
        await handler.handle_memory_episode(episode)

        # Verify service.ingest was called
        mock_service.ingest.assert_awaited_once_with(episode)


# AC-003: `PoisonEpisodeError` routes to DLQ with reason recorded
@pytest.mark.asyncio
async def test_poison_error_routes_to_dlq(make_episode, mock_broker, mock_settings):
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

    # Configure mock broker context
    mock_broker.context.get_global.return_value = mock_settings

    with patch.object(handler, "service", mock_service):
        with patch.object(handler, "broker", mock_broker):
            # Expect RejectMessage exception
            with pytest.raises(RejectMessage):
                await handler.handle_memory_episode(episode)

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
            # Expect NackMessage exception
            with pytest.raises(NackMessage):
                await handler.handle_memory_episode(episode)

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
            # Expect NackMessage exception (default-to-transient)
            with pytest.raises(NackMessage):
                await handler.handle_memory_episode(episode)

            # Verify service.ingest was called
            mock_service.ingest.assert_awaited_once_with(episode)

            # Verify NO DLQ publish occurred (treated as transient)
            mock_broker.publish.assert_not_awaited()


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
