"""Accounting invariant for the relay: published == stored + dlq (no silent gap).

The 2026-06-26 harvest lost 109/447 episodes because deterministic embed-400s were
classified transient and nak-retried into a silent max_deliver drop (neither stored
nor dead-lettered). The defining property of the fix is an *accounting* one: every
published episode must end up either stored or visible in the DLQ — never silently
gone (TASK-FIX-RELAYDROP01).

This component test drives the REAL handler + REAL RelayService classification (the
embed server's deterministic 400 is injected as EmbedRequestError) with fake writers
and an in-memory DLQ capture, so it runs in the standard suite. The sibling
integration test (tests/integration/test_relay_dlq_invariant.py) asserts the same
invariant against a real Postgres store.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from faststream.exceptions import NackMessage, RejectMessage

from fleet_memory.errors import EmbedRequestError
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.relay.service import RelayService
from fleet_memory.settings import Settings


def _episode(episode_id: str, project_id: str = "invariant_proj") -> MemoryEpisodeV1:
    """A single-chunk prose episode (short body → exactly one chunk)."""
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
    """Stand-in for the injected NatsMessage (first delivery by default)."""
    msg = Mock()
    msg.raw_message.metadata.num_delivered = num_delivered
    return msg


class _RecordingChunkWriter:
    """Fake ChunkWriter: records stored episode_ids, 400s the designated poison ones.

    The embed server returns a deterministic HTTP 400 (exceed_context_size_error) for
    over-n_ctx input; we inject that as EmbedRequestError on write so the REAL
    RelayService runs its actual classification (EmbedRequestError → PoisonEpisodeError).
    """

    def __init__(self, poison_ids: set[str]) -> None:
        self.poison_ids = poison_ids
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


@pytest.mark.asyncio
async def test_published_equals_stored_plus_dlq_no_silent_gap():
    """Every published episode is accounted for as stored XOR dead-lettered.

    A 50/50 mix of good and over-n_ctx episodes is driven through the real handler.
    The invariant: published == stored + dlq, with the stored and dlq id-sets disjoint
    and together covering every published id — i.e. nothing is silently dropped.
    """
    from fleet_memory.relay import handler

    good_ids = {f"good-{i}" for i in range(6)}
    poison_ids = {f"oversized-{i}" for i in range(4)}
    published_ids = good_ids | poison_ids

    chunk_writer = _RecordingChunkWriter(poison_ids=poison_ids)
    settings = Mock(spec=Settings)
    settings.chunk_target_tokens = 1000
    settings.chunk_overlap_ratio = 0.15
    service = RelayService(
        writer=AsyncMock(), chunk_writer=chunk_writer, settings=settings
    )

    mock_broker = AsyncMock()

    dlq_ids: set[str] = set()
    nak_ids: set[str] = set()

    with patch.object(handler, "service", service):
        with patch.object(handler, "broker", mock_broker):
            for episode_id in sorted(published_ids):
                episode = _episode(episode_id)
                try:
                    await handler.handle_memory_episode(episode, _msg())
                except RejectMessage:
                    pass  # poison → DLQ + term (recorded via broker.publish below)
                except NackMessage:
                    nak_ids.add(episode_id)  # would redeliver — NOT terminal

    # Reconstruct the DLQ ledger from what the handler published to memory.dlq.>
    for call in mock_broker.publish.call_args_list:
        subject = call.kwargs.get("subject", "")
        if subject.startswith("memory.dlq."):
            dlq_ids.add(call.args[0]["episode_id"])

    stored_ids = set(chunk_writer.stored_ids)

    # The accounting invariant: published == stored + dlq, exactly.
    assert stored_ids == good_ids
    assert dlq_ids == poison_ids
    assert len(stored_ids) + len(dlq_ids) == len(published_ids)
    # Disjoint and total-covering: no episode both stored and DLQ'd; none left in limbo.
    assert stored_ids.isdisjoint(dlq_ids)
    assert stored_ids | dlq_ids == published_ids
    # No episode ended in a non-terminal nak state (which on a real consumer is the
    # silent-drop risk this task closes).
    assert nak_ids == set()


@pytest.mark.asyncio
async def test_no_silent_gap_when_all_episodes_are_poison():
    """If every episode deterministically 400s, all land in the DLQ (none vanish)."""
    from fleet_memory.relay import handler

    poison_ids = {f"oversized-{i}" for i in range(5)}

    chunk_writer = _RecordingChunkWriter(poison_ids=poison_ids)
    settings = Mock(spec=Settings)
    settings.chunk_target_tokens = 1000
    settings.chunk_overlap_ratio = 0.15
    service = RelayService(
        writer=AsyncMock(), chunk_writer=chunk_writer, settings=settings
    )
    mock_broker = AsyncMock()

    dlq_ids: set[str] = set()
    with patch.object(handler, "service", service):
        with patch.object(handler, "broker", mock_broker):
            for episode_id in sorted(poison_ids):
                with pytest.raises(RejectMessage):
                    await handler.handle_memory_episode(_episode(episode_id), _msg())

    for call in mock_broker.publish.call_args_list:
        if call.kwargs.get("subject", "").startswith("memory.dlq."):
            dlq_ids.add(call.args[0]["episode_id"])

    assert dlq_ids == poison_ids
    assert chunk_writer.stored_ids == []
    # Every published episode is in the DLQ — zero silently dropped.
    assert len(dlq_ids) == len(poison_ids)
