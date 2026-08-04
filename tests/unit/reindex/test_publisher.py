"""Unit tests for the JetStream reindex publisher — the vanishing-publish fix.

The old publisher wrote to subject "MEMORY" through fleet_memory.app.broker: a
core-NATS publish NOTHING captures (the MEMORY stream binds memory.episode.>).
These tests pin the corrected contract: partitioned subject, Nats-Msg-Id
deduplication header, size guard, fail-loud configuration, and independence
from the app broker.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleet_memory.payloads.models import BuildOutcomePayload
from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.reindex.publisher import (
    MAX_EPISODE_BODY_BYTES,
    ReindexPublisher,
    ReindexPublishError,
    _derive_episode_id,
    episode_subject,
    publish_episode,
)
from fleet_memory.relay.schema import MemoryEpisodeV1


def _make_payload(**overrides) -> BuildOutcomePayload:
    defaults = {
        "project": "guardkit",
        "identifier": "TASK_FIX_RESUMEVENV01",
        "status": "success",
        "duration_seconds": 0,
        "task_id": "TASK_FIX_RESUMEVENV01",
        "source_ref": "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md",
        "domain_tags": ["task", "fm-status:completed"],
    }
    defaults.update(overrides)
    return BuildOutcomePayload(**defaults)


def _make_settings(publish_url: str = "nats://publish:4222") -> MagicMock:
    settings = MagicMock()
    settings.publish_nats_url = publish_url
    return settings


def _connected_publisher() -> tuple[ReindexPublisher, AsyncMock]:
    publisher = ReindexPublisher(_make_settings())
    fake_js = AsyncMock()
    publisher._js = fake_js
    return publisher, fake_js


class TestSubjectContract:
    """Published subjects must land inside the MEMORY stream's filter."""

    async def test_subject_is_partitioned(self) -> None:
        publisher, fake_js = _connected_publisher()
        await publisher.publish(_make_payload())

        subject = fake_js.publish.call_args[0][0]
        assert subject == "memory.episode.guardkit.build_outcome"

    def test_episode_subject_helper(self) -> None:
        assert (
            episode_subject("guardkit", "build_outcome")
            == "memory.episode.guardkit.build_outcome"
        )

    async def test_subject_matches_relay_consumer_filter(self) -> None:
        """REGRESSION (the ops refuter's kill): the subject must match the
        relay's memory.episode.> filter — subject "MEMORY" matched nothing."""
        publisher, fake_js = _connected_publisher()
        await publisher.publish(_make_payload())

        subject = fake_js.publish.call_args[0][0]
        # memory.episode.> matches subjects with the two-token prefix and at
        # least one more token
        prefix_tokens = subject.split(".")
        assert prefix_tokens[:2] == ["memory", "episode"]
        assert len(prefix_tokens) >= 3
        assert subject != "MEMORY"


class TestEnvelopeContract:
    """Envelope fields route the episode to the DeterministicWriter."""

    async def test_envelope_shape(self) -> None:
        publisher, fake_js = _connected_publisher()
        payload = _make_payload()
        await publisher.publish(payload)

        raw = fake_js.publish.call_args[0][1]
        envelope = json.loads(raw)

        assert envelope["project_id"] == "guardkit"  # canonical field
        assert envelope["episode_type"] == "build_outcome"
        assert envelope["payload_type"] == "build_outcome"
        assert envelope["content_format"] == "json"
        assert envelope["source_ref"] == payload.source_ref

        # The relay schema accepts the envelope as-is
        episode = MemoryEpisodeV1(**envelope)
        assert episode.project_id == "guardkit"

    async def test_body_round_trips_through_registry(self) -> None:
        publisher, fake_js = _connected_publisher()
        payload = _make_payload(lessons="Distilled lesson prose")
        await publisher.publish(payload)

        envelope = json.loads(fake_js.publish.call_args[0][1])
        model_class = get_model_for_type(envelope["payload_type"])
        reconstructed = model_class(**json.loads(envelope["body"]))
        assert reconstructed == payload

    async def test_msg_id_header_shape(self) -> None:
        """Nats-Msg-Id carries the deterministic episode_id (JetStream dedup)."""
        publisher, fake_js = _connected_publisher()
        payload = _make_payload()
        await publisher.publish(payload)

        headers = fake_js.publish.call_args.kwargs["headers"]
        msg_id = headers["Nats-Msg-Id"]
        assert re.fullmatch(r"ep-[0-9a-f]{16}", msg_id)
        assert msg_id == _derive_episode_id(payload.natural_key)

    def test_derive_episode_id_prefix(self) -> None:
        """The one id-minting rule: 'ep-' + first 16 hex of sha256(natural_key)."""
        episode_id = _derive_episode_id("build_outcome:guardkit:TASK_1")
        assert episode_id.startswith("ep-")
        assert len(episode_id) == 19

    async def test_same_natural_key_same_episode_id(self) -> None:
        publisher, fake_js = _connected_publisher()
        await publisher.publish(_make_payload())
        first = json.loads(fake_js.publish.call_args[0][1])["episode_id"]
        await publisher.publish(_make_payload())
        second = json.loads(fake_js.publish.call_args[0][1])["episode_id"]
        assert first == second


class TestSizeGuard:
    """Oversized payloads are skipped with a named reason, mirroring harvest."""

    async def test_oversized_payload_skipped_with_reason(self) -> None:
        publisher, fake_js = _connected_publisher()
        payload = _make_payload(lessons="x" * (MAX_EPISODE_BODY_BYTES + 100))

        reason = await publisher.publish(payload)

        assert reason is not None
        assert "MAX_EPISODE_BODY_BYTES" in reason
        fake_js.publish.assert_not_awaited()

    async def test_normal_payload_returns_none(self) -> None:
        publisher, fake_js = _connected_publisher()
        assert await publisher.publish(_make_payload()) is None
        fake_js.publish.assert_awaited_once()


class TestFailLoudConfiguration:
    """A publish run with nowhere to publish dies before walking."""

    def test_unset_publish_url_fails_at_construction(self) -> None:
        with pytest.raises(ReindexPublishError, match="FLEET_MEMORY_PUBLISH_NATS_URL"):
            ReindexPublisher(_make_settings(publish_url=""))

    async def test_publish_before_connect_fails_loud(self) -> None:
        publisher = ReindexPublisher(_make_settings())
        with pytest.raises(ReindexPublishError, match="before connect"):
            await publisher.publish(_make_payload())

    async def test_publish_episode_without_active_publisher_fails_loud(self) -> None:
        with pytest.raises(ReindexPublishError, match="No active ReindexPublisher"):
            await publish_episode(_make_payload())


class TestBrokerIndependence:
    """The publisher NEVER touches fleet_memory.app.broker."""

    def test_module_has_no_broker_reference(self) -> None:
        import fleet_memory.reindex.publisher as publisher_module

        assert not hasattr(publisher_module, "broker")

    def test_module_source_never_imports_app_broker(self) -> None:
        import inspect

        import fleet_memory.reindex.publisher as publisher_module

        source = inspect.getsource(publisher_module)
        assert "from fleet_memory.app import" not in source
