"""JetStream DLQ membership client for audit reconciliation.

Reads the MEMORY stream's per-project dead-letter subject
(``memory.dlq.{project}``) with an ephemeral ordered consumer
(deliver_policy=all) and builds a membership set of episode_ids. The relay's
handler publishes the episode_id inside the JSON message BODY
(handler._publish_dlq) — that is where this client parses it from, not from
headers or the subject.

Connection identity: uses settings.nats_url (the consumer identity — reading is
what it can do). The reindex PUBLISHER uses settings.publish_nats_url; the two
paths never share credentials.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleet_memory.settings import Settings

# Stream that captures memory.episode.> and memory.dlq.> (provisioned by
# nats-infrastructure; this client only reads).
MEMORY_STREAM_NAME = "MEMORY"

# Seconds to wait for the next DLQ message before concluding the subject is drained
_DRAIN_TIMEOUT_S = 2.0


def parse_episode_id(data: bytes) -> str | None:
    """Parse the episode_id from a DLQ message body.

    handler._publish_dlq puts the episode_id in the JSON BODY of the DLQ
    message — this is the single parsing rule the audit relies on.

    Args:
        data: Raw DLQ message payload bytes

    Returns:
        The episode_id string, or None when the body is not a JSON object
        carrying one (malformed DLQ entries are counted as absent, never crash
        the audit)
    """
    try:
        body = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    episode_id = body.get("episode_id")
    return str(episode_id) if episode_id else None


class JetStreamDLQClient:
    """Membership client over the per-project DLQ subject on the MEMORY stream.

    Loads all DLQ entries once (ephemeral ordered consumer, deliver_policy=all)
    and answers membership queries from the resulting set.
    """

    def __init__(self, settings: Settings, project: str) -> None:
        """Initialize the client.

        Args:
            settings: Fleet-memory settings (nats_url is the consumer identity)
            project: Project whose DLQ subject to read (memory.dlq.{project})
        """
        self._url = settings.nats_url
        self._subject = f"{settings.dlq_subject}.{project}"
        self._episode_ids: set[str] | None = None

    def ingest(self, payloads: list[bytes]) -> set[str]:
        """Build the membership set from raw DLQ message payloads.

        Split out from load() so the parsing/membership rule is testable without
        a live broker (the round-trip test feeds handler-shaped payloads here).

        Args:
            payloads: Raw DLQ message bodies

        Returns:
            The episode_id membership set (also cached on the client)
        """
        episode_ids: set[str] = set()
        for data in payloads:
            episode_id = parse_episode_id(data)
            if episode_id is not None:
                episode_ids.add(episode_id)
        self._episode_ids = episode_ids
        return episode_ids

    async def load(self) -> set[str]:
        """Read the full DLQ subject and build the episode_id membership set.

        Creates an ephemeral ordered consumer on the MEMORY stream filtered to
        memory.dlq.{project} with deliver_policy=all, drains it, and parses the
        episode_id from each JSON body.

        Returns:
            The episode_id membership set (also cached on the client)
        """
        import nats
        from nats.errors import TimeoutError as NatsTimeoutError
        from nats.js.api import ConsumerConfig, DeliverPolicy

        payloads: list[bytes] = []

        nc = await nats.connect(self._url)
        try:
            js = nc.jetstream()
            subscription = await js.subscribe(
                self._subject,
                stream=MEMORY_STREAM_NAME,
                ordered_consumer=True,
                config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
            )
            try:
                while True:
                    try:
                        msg = await subscription.next_msg(timeout=_DRAIN_TIMEOUT_S)
                    except NatsTimeoutError:
                        break
                    payloads.append(msg.data)
            finally:
                await subscription.unsubscribe()
        finally:
            await nc.close()

        return self.ingest(payloads)

    async def check_episode_on_dlq(self, episode_id: str) -> bool:
        """Check membership; loads the DLQ set on first use.

        Args:
            episode_id: Episode ID to check ("ep-" + 16 hex chars)

        Returns:
            True if the episode is on the dead-letter queue
        """
        if self._episode_ids is None:
            await self.load()
        assert self._episode_ids is not None
        return episode_id in self._episode_ids
