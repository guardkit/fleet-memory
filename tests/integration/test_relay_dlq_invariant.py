"""Integration: relay accounting invariant against a REAL Postgres store.

Marker-gated (@pytest.mark.integration) — requires Docker for the ephemeral_pg
fixture; the default `pytest` run skips it (run with: pytest -m integration).

Proves the property that the 2026-06-26 harvest violated (109/447 episodes silently
lost): for a memory write path, **published == stored + dlq, with no silent gap**.
Every published episode must end up either durably stored or visible in the DLQ.

Fidelity vs the unit-level sibling (tests/unit/relay/test_relay_dlq_invariant.py):
this drives the REAL RelayService + REAL ChunkWriter writing to a REAL pgvector store
through the REAL handler. Only two things are stand-ins:
  - the embed server's deterministic HTTP 400 is injected as EmbedRequestError for
    over-n_ctx inputs (mirrors test_embed_failures.py's failing-embed injection);
  - the NATS transport is an AsyncMock, since the integration harness provisions
    Postgres but not a JetStream broker — so the handler's DLQ publish is captured
    in-process rather than round-tripped through `memory.dlq.>`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from faststream.exceptions import NackMessage, RejectMessage

from fleet_memory.embed import make_fake_embed
from fleet_memory.errors import EmbedRequestError
from fleet_memory.relay.chunk_writer import ChunkWriter
from fleet_memory.relay.schema import MemoryEpisodeV1
from fleet_memory.relay.service import RelayService
from fleet_memory.store import async_store_context
from fleet_memory.writer.core import DeterministicWriter

# Sentinel embedded in over-budget bodies; the injected embed callable 400s on it,
# faithfully reproducing the embed server's deterministic exceed_context_size_error.
_OVERSIZED_SENTINEL = "__EXCEEDS_N_CTX__"


def _episode(episode_id: str, *, project: str, oversized: bool) -> MemoryEpisodeV1:
    """A single-chunk prose episode; oversized ones carry the n_ctx sentinel."""
    body = f"Prose body for {episode_id}."
    if oversized:
        body = f"{body} {_OVERSIZED_SENTINEL}"
    return MemoryEpisodeV1(
        episode_id=episode_id,
        project_id=project,
        episode_type="document",
        content_format="text",
        body=body,
        payload_type=None,
        source_ref=f"ref://{episode_id}",
    )


def _msg(num_delivered: int = 1) -> Mock:
    """Stand-in for the injected NatsMessage (first delivery)."""
    msg = Mock()
    msg.raw_message.metadata.num_delivered = num_delivered
    return msg


@pytest.mark.integration
async def test_published_equals_stored_plus_dlq_against_real_store(test_settings) -> None:
    """published == stored + dlq, counted from real pgvector rows — no silent gap.

    Drives a mix of good and over-n_ctx episodes through the real handler/service/
    ChunkWriter against a real Postgres store. Asserts that the durably stored
    episode-ids and the dead-lettered episode-ids are disjoint and together cover
    every published id, with the stored count read back from actual rows.
    """
    from fleet_memory.relay import handler

    # Per-test project namespace (ephemeral_pg is session-scoped, so isolate this
    # test's chunk rows from any sibling that shares the DB — mirrors conftest's
    # store_context test_<uuid> convention).
    project = f"invariant_{uuid4().hex[:8]}"
    good_ids = {f"good-{i}" for i in range(6)}
    oversized_ids = {f"oversized-{i}" for i in range(4)}
    published_ids = good_ids | oversized_ids

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)

    async def poison_aware_embed(texts: list[str]) -> list[list[float]]:
        """Deterministic 400 for over-n_ctx inputs; fake vectors otherwise."""
        if any(_OVERSIZED_SENTINEL in t for t in texts):
            raise EmbedRequestError(
                "the request exceeds the available context size (n_ctx=2048)",
                url=test_settings.embed_url,
                status_code=400,
                error_type="exceed_context_size_error",
            )
        return await fake_embed(texts)

    mock_broker = AsyncMock()
    namespace_prefix = ("fleet_memory", project, "chunk")

    async with async_store_context(test_settings, embed_fn=poison_aware_embed) as store:
        service = RelayService(
            writer=DeterministicWriter(store=store, settings=test_settings),
            chunk_writer=ChunkWriter(store=store),
            settings=test_settings,
        )

        dlq_ids: set[str] = set()
        nak_ids: set[str] = set()
        with patch.object(handler, "service", service):
            with patch.object(handler, "broker", mock_broker):
                # Ingest strictly one episode at a time: each await drains its own
                # store batch tick, so a poison episode's embed failure can never be
                # co-batched with (and thus contaminate) a good episode's write.
                for episode_id in sorted(published_ids):
                    episode = _episode(
                        episode_id,
                        project=project,
                        oversized=episode_id in oversized_ids,
                    )
                    try:
                        await handler.handle_memory_episode(episode, _msg())
                    except RejectMessage:
                        pass  # poison → DLQ + term (terminal, recorded below)
                    except NackMessage:
                        nak_ids.add(episode_id)  # non-terminal: the silent-drop risk

        # DLQ ledger: what the handler published to memory.dlq.>
        for call in mock_broker.publish.call_args_list:
            if call.kwargs.get("subject", "").startswith("memory.dlq."):
                dlq_ids.add(call.args[0]["episode_id"])

        # Stored ledger: read back actual rows from pgvector (each good → one chunk)
        stored_items = await store.asearch(namespace_prefix, limit=1000)
        stored_ids = {item.value["episode_id"] for item in stored_items}

    # The accounting invariant, against real persisted state:
    assert stored_ids == good_ids, "every good episode is durably stored"
    assert dlq_ids == oversized_ids, "every over-n_ctx episode is dead-lettered"
    # Exactly one chunk row per good episode — pins down fan-out/duplication regressions
    # that the set form of stored_ids would otherwise collapse and hide.
    assert len(stored_items) == len(good_ids)
    # Disjoint + total-covering: nothing both stored and DLQ'd; nothing silently lost.
    assert stored_ids.isdisjoint(dlq_ids)
    assert stored_ids | dlq_ids == published_ids
    assert len(stored_ids) + len(dlq_ids) == len(published_ids)
    # No partial write for a poison episode: it left zero rows behind.
    assert oversized_ids.isdisjoint(stored_ids)
    # No episode left in a non-terminal nak state (a real consumer would silently
    # drop it at max_deliver) — the exact failure class this task closes.
    assert nak_ids == set()


@pytest.mark.integration
async def test_dlq_records_name_the_deterministic_cause(test_settings) -> None:
    """A dead-lettered over-n_ctx episode carries a self-describing reason.

    Operability: the DLQ record must say *why* (the server's error type) so a human
    triaging memory.dlq.> can act without re-deriving the failure.
    """
    from fleet_memory.relay import handler

    project = f"invariant_{uuid4().hex[:8]}"

    async def always_exceed_embed(texts: list[str]) -> list[list[float]]:
        raise EmbedRequestError(
            "the request exceeds the available context size (n_ctx=2048)",
            url=test_settings.embed_url,
            status_code=400,
            error_type="exceed_context_size_error",
        )

    mock_broker = AsyncMock()

    async with async_store_context(test_settings, embed_fn=always_exceed_embed) as store:
        service = RelayService(
            writer=DeterministicWriter(store=store, settings=test_settings),
            chunk_writer=ChunkWriter(store=store),
            settings=test_settings,
        )
        with patch.object(handler, "service", service):
            with patch.object(handler, "broker", mock_broker):
                with pytest.raises(RejectMessage):
                    await handler.handle_memory_episode(
                        _episode("oversized-solo", project=project, oversized=True),
                        _msg(),
                    )

    mock_broker.publish.assert_awaited_once()
    payload = mock_broker.publish.call_args.args[0]
    assert payload["episode_id"] == "oversized-solo"
    assert "exceed_context_size_error" in payload["reason"]
    assert mock_broker.publish.call_args.kwargs["subject"] == f"memory.dlq.{project}"
