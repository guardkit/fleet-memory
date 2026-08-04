"""Unit tests for the JetStream DLQ membership client.

The episode_id lives in the JSON message BODY (that is where the relay's
handler._publish_dlq puts it) — never in headers or the subject.
"""

from __future__ import annotations

import json

from fleet_memory.reindex.dlq_client import JetStreamDLQClient, parse_episode_id


class _Settings:
    nats_url = "nats://consumer:4222"
    dlq_subject = "memory.dlq"


class TestParseEpisodeId:
    """The single parsing rule over handler-shaped DLQ payloads."""

    def test_parses_episode_id_from_json_body(self) -> None:
        payload = json.dumps(
            {
                "episode_id": "ep-0123456789abcdef",
                "project_id": "guardkit",
                "reason": "poison",
                "detail": "bad identifier",
            }
        ).encode("utf-8")
        assert parse_episode_id(payload) == "ep-0123456789abcdef"

    def test_missing_episode_id_returns_none(self) -> None:
        assert parse_episode_id(json.dumps({"reason": "poison"}).encode()) is None

    def test_non_object_body_returns_none(self) -> None:
        assert parse_episode_id(json.dumps(["ep-1"]).encode()) is None
        assert parse_episode_id(json.dumps("ep-1").encode()) is None

    def test_malformed_json_returns_none(self) -> None:
        assert parse_episode_id(b"{not json") is None
        assert parse_episode_id(b"\xff\xfe") is None


class TestMembership:
    """Membership set semantics."""

    def test_ingest_builds_membership_set(self) -> None:
        client = JetStreamDLQClient(_Settings(), "guardkit")
        payloads = [
            json.dumps({"episode_id": "ep-aaaaaaaaaaaaaaaa"}).encode(),
            json.dumps({"episode_id": "ep-bbbbbbbbbbbbbbbb"}).encode(),
            b"{malformed",  # counted as absent, never crashes the audit
        ]
        ids = client.ingest(payloads)
        assert ids == {"ep-aaaaaaaaaaaaaaaa", "ep-bbbbbbbbbbbbbbbb"}

    async def test_check_episode_on_dlq_after_ingest(self) -> None:
        client = JetStreamDLQClient(_Settings(), "guardkit")
        client.ingest([json.dumps({"episode_id": "ep-cccccccccccccccc"}).encode()])

        assert await client.check_episode_on_dlq("ep-cccccccccccccccc") is True
        assert await client.check_episode_on_dlq("ep-dddddddddddddddd") is False

    def test_subject_is_per_project(self) -> None:
        client = JetStreamDLQClient(_Settings(), "guardkit")
        assert client._subject == "memory.dlq.guardkit"

    def test_uses_consumer_identity_url(self) -> None:
        """Reading uses settings.nats_url — the consumer identity, never the
        publish credentials."""
        client = JetStreamDLQClient(_Settings(), "guardkit")
        assert client._url == "nats://consumer:4222"
