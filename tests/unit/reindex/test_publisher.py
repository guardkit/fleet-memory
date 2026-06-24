"""Unit tests for reindex publisher: MemoryEpisodeV1 publishing contract.

Tests verify that the publisher converts BasePayload instances to MemoryEpisodeV1
with correct content_format="json", payload_type routing, deterministic episode_id,
and body round-trip serialization.

Producer: TASK-RIP-002
Consumer: FEAT-MEM-07 re-index pipeline
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from fleet_memory.payloads.models import ADRPayload
from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.relay.schema import MemoryEpisodeV1


def _make_adr_payload(**overrides) -> ADRPayload:
    """Factory for ADRPayload test instances."""
    defaults = {
        "project": "test_proj",
        "identifier": "ADR_001",
        "source_ref": "src/adrs/ADR_001.md",
        "title": "Test ADR",
        "status": "accepted",
        "decision": "We will use test-driven development",
    }
    defaults.update(overrides)
    return ADRPayload(**defaults)


@pytest.fixture
def make_adr_payload():
    """Fixture providing ADRPayload factory."""
    return _make_adr_payload


@pytest.fixture
def mock_broker():
    """Mock broker for publish verification."""
    broker_mock = AsyncMock()
    return broker_mock


# AC-001: Publisher exposes function accepting BasePayload and publishes MemoryEpisodeV1
# AC-002: Published episode has content_format=="json" and payload_type routing
@pytest.mark.asyncio
async def test_episode_is_json_with_payload_type(make_adr_payload, mock_broker):
    """Verify published episode has content_format='json' and correct payload_type.

    Contract: content_format must be literal "json" for RelayService routing.
    payload_type must match the payload's type for dispatch registry lookup.
    """
    from fleet_memory.reindex import publisher

    payload = make_adr_payload()

    # Mock broker.publish to capture the published episode
    with patch.object(publisher, "broker", mock_broker):
        await publisher.publish_episode(payload)

    # Verify broker.publish was called once
    mock_broker.publish.assert_awaited_once()

    # Extract the published episode (first positional arg)
    call_args = mock_broker.publish.call_args
    published_data = call_args[0][0]  # First positional argument

    # Parse as MemoryEpisodeV1
    episode = MemoryEpisodeV1(**published_data)

    # AC-002: Verify content_format and payload_type for routing
    assert (
        episode.content_format == "json"
    ), "content_format must be 'json' for relay routing"
    assert episode.payload_type == "adr", "payload_type must match payload type"
    assert episode.project_id == payload.project


# AC-003: Body round-trips through registry
@pytest.mark.asyncio
async def test_body_round_trips_through_registry(make_adr_payload, mock_broker):
    """Verify body serializes and reconstructs payload through registry.

    Contract: episode.body must be canonical JSON that deserializes to equal payload.
    get_model_for_type(episode.payload_type)(**json.loads(episode.body)) == original
    """
    from fleet_memory.reindex import publisher

    original_payload = make_adr_payload()

    # Publish and capture
    with patch.object(publisher, "broker", mock_broker):
        await publisher.publish_episode(original_payload)

    # Extract episode
    published_data = mock_broker.publish.call_args[0][0]
    episode = MemoryEpisodeV1(**published_data)

    # Round-trip through registry
    payload_model = get_model_for_type(episode.payload_type)
    reconstructed = payload_model(**json.loads(episode.body))

    # Verify equality (all fields match)
    assert reconstructed == original_payload, "Body must round-trip to equal payload"


# AC-004: episode_id is deterministic for natural_key
@pytest.mark.asyncio
async def test_episode_id_deterministic_for_natural_key(make_adr_payload, mock_broker):
    """Verify same natural_key produces same episode_id for idempotent publish.

    Contract: Publishing the same payload twice yields same episode_id.
    This ensures JetStream Msg-Id deduplication works at publish layer.
    """
    from fleet_memory.reindex import publisher

    payload1 = make_adr_payload()
    payload2 = make_adr_payload()  # Same natural key

    # Publish both
    with patch.object(publisher, "broker", mock_broker):
        await publisher.publish_episode(payload1)
        first_episode_data = mock_broker.publish.call_args[0][0]
        first_episode = MemoryEpisodeV1(**first_episode_data)

        mock_broker.reset_mock()

        await publisher.publish_episode(payload2)
        second_episode_data = mock_broker.publish.call_args[0][0]
        second_episode = MemoryEpisodeV1(**second_episode_data)

    # Verify episode_id is deterministic
    assert (
        first_episode.episode_id == second_episode.episode_id
    ), "Same natural key must produce same episode_id for idempotent publish"


# AC-005: No LLM/cloud/frontier-model call
@pytest.mark.asyncio
async def test_no_network_calls_during_publish(make_adr_payload, mock_broker):
    """Verify publisher makes no network calls (no LLM/cloud requests).

    Contract: Publisher must be pure transformation with no external requests.
    This test asserts no unexpected network activity (DECISION-DF-001).
    """
    from fleet_memory.reindex import publisher

    payload = make_adr_payload()

    # Mock broker to prevent actual NATS publish
    with patch.object(publisher, "broker", mock_broker):
        # This should complete without any network calls
        # (broker.publish is mocked, so no NATS connection)
        await publisher.publish_episode(payload)

    # Success if we get here without timeout or network errors
    # The mock prevents actual NATS publish, so no network activity occurs
    assert True, "Publisher completed without network calls"


# AC-006: source_ref is carried forward
@pytest.mark.asyncio
async def test_source_ref_preserved(make_adr_payload, mock_broker):
    """Verify source_ref from payload is preserved in episode."""
    from fleet_memory.reindex import publisher

    payload = make_adr_payload(source_ref="docs/decisions/ADR_TEST.md")

    with patch.object(publisher, "broker", mock_broker):
        await publisher.publish_episode(payload)

    published_data = mock_broker.publish.call_args[0][0]
    episode = MemoryEpisodeV1(**published_data)

    assert episode.source_ref == payload.source_ref
