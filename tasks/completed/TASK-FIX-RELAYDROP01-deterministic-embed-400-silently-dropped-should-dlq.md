---
id: TASK-FIX-RELAYDROP01
title: Relay silently drops deterministic embed-400 (exceed_context) — should poison→DLQ, not transient→nack
task_type: fix
status: completed
created: 2026-06-26T00:00:00+00:00
updated: 2026-06-26T00:00:00+00:00
completed: 2026-06-26T00:00:00+00:00
previous_state: in_review
priority: high
tags:
  - relay
  - reliability
  - dlq
  - absence-of-failure
  - harvest-incident
related:
  - TASK-FIX-EMBEDCTX01
  - TASK-FIX-RELAYBATCH01
---

# Relay silently drops deterministic embed failures

## Incident (2026-06-26)

109 of 447 episodes vanished during the first live harvest: **not stored, not in
the DLQ**, and the consumer reported fully drained. A silent data loss — the most
dangerous failure mode for a memory write path (you cannot tell harvest succeeded
from harvest-lost-a-quarter-of-itself without counting rows).

## Root cause (this task's half)

The embed server returns a **deterministic** HTTP 400
(`exceed_context_size_error`, n_ctx=2048) for over-budget requests
([[TASK-FIX-EMBEDCTX01]] / [[TASK-FIX-RELAYBATCH01]]). The relay maps this to a
**transient** failure:

- `embed.py` 400 → `EmbedServiceError`
- `relay/service.py::ingest` → `EmbedServiceError` falls into the recoverable
  bucket → `TransientIngestError`
- `relay/handler.py`: `TransientIngestError → NackMessage` (redeliver up to
  `max_deliver=5`)

So the episode nacks 5× (re-failing identically each time — it is deterministic),
then JetStream stops redelivering. Crucially, **max-deliver exhaustion is NOT the
explicit `RejectMessage`/DLQ path** (only `PoisonEpisodeError` publishes to
`dlq_subject`). The message is effectively ack-dropped: gone, invisible.

This is an instance of the *absence-of-failure-is-not-success* family — a
deterministic, classifiable failure routed to a transient retry that silently
exhausts.

## Fix direction

1. **Classify a deterministic embed 400 (`exceed_context_size_error`, and other
   4xx that won't change on retry) as `PoisonEpisodeError` → RejectMessage →
   explicit DLQ publish**, so the failure is *visible* (in `memory.dlq.>`) rather
   than silently dropped. Distinguish from genuinely transient embed failures
   (timeouts, 5xx, connection errors → keep `TransientIngestError`).
2. **Make max-deliver exhaustion loud regardless of classification**: when a
   durable-consumer message hits `max_deliver` without an ack, publish it to the
   DLQ (or a `max_deliver_exhausted` advisory) + log at WARNING — never let a
   message leave the consumer un-acked-and-unrecorded. A memory write path must
   not lose data silently under any classification bug.
3. Pair with the real fix ([[TASK-FIX-RELAYBATCH01]] + [[TASK-FIX-EMBEDCTX01]]) so
   these episodes *succeed*; this task ensures that if anything still fails, it
   fails **loudly**.

## Verification

Reproducer: feed an over-`n_ctx` episode; assert it lands in `memory.dlq.>` (not
silently dropped) with a clear reason, and a metric/log records it. Add a
post-harvest invariant check: `published == stored + dlq` (no silent gap).

## Recovery for the 2026-06-26 incident

After [[TASK-FIX-EMBEDCTX01]]/[[TASK-FIX-RELAYBATCH01]] land, recreate/redeliver
the durable consumer over the still-intact MEMORY stream (447 msgs, seq 19–465);
`ChunkWriter` idempotency (`uuid5(episode_id, index)`) makes the replay safe.

## Implementation (2026-06-26)

Two independent guards, verified by the unit suite (607 passed, 0 failed) AND by
the new marker-gated integration tests run against a real ephemeral pgvector store
(`pytest -m integration` → 2 passed). The integration suite is *deselected by
default*, not unavailable: Docker is present on the GB10 host and the `ephemeral_pg`
fixture provisions its own throwaway pgvector container.

**1. Classify deterministic embed 4xx as poison → DLQ.**
- `errors.py`: new `EmbedRequestError(EmbedServiceError)` — a deterministic 4xx
  (e.g. `exceed_context_size_error`) carrying `status_code` + server `error_type`.
  Subclassing keeps read-path callers that catch `EmbedServiceError` working.
- `embed.py`: `_embed_request` now splits non-200s. `_is_deterministic_client_error`
  routes 4xx **except 408/429** to `EmbedRequestError`; 5xx/408/429 stay
  transient `EmbedServiceError`. `_parse_embed_error` lifts the server's
  `error.type`/`error.message` (OpenAI/llama.cpp envelope) for the DLQ record.
- `service.py`: `ingest` catches `EmbedRequestError` **before** the transient
  `(EmbedServiceError, EmbedTimeoutError)` clause → `PoisonEpisodeError` whose
  reason names the HTTP code + error type. Handler then publishes to
  `memory.dlq.{project_id}` and terms (existing poison path).

**2. Max-deliver exhaustion is now loud (any classification).**
- `handler.py`: handler injects the raw `NatsMessage` and reads
  `raw_message.metadata.num_delivered`. New `_route_transient` naks while
  `num_delivered < max_deliver`, but on the **final** delivery publishes to the
  DLQ (`reason: max_deliver_exhausted`, `failure_mode`, `delivery_count`) and
  terms — so a persistent "transient" failure (or a classification bug) surfaces
  in `memory.dlq.>` instead of silently ack-dropping. Applies to both
  `TransientIngestError` and the default-to-transient unenumerated path. DLQ
  writes consolidated in `_publish_dlq`. `_delivery_count` defends against
  missing metadata (returns 0 → nak, never a spurious term).

**Tests added/updated:** `test_embed.py` (4xx vs 408/429/5xx classification +
`exceed_context_size_error` reproducer), `test_errors.py` (`EmbedRequestError`
taxonomy), `test_service.py` (`EmbedRequestError → poison` on json + prose paths),
`test_handler.py` (exhaustion → DLQ+term for transient & unenumerated, not-yet-
exhausted still naks, missing-metadata fallback, and an end-to-end
deterministic-embed-400 → `memory.dlq.>` reproducer through a real `RelayService`).

**3. Accounting invariant `published == stored + dlq` (no silent gap).** Two
new files encode the property the harvest violated — every published episode is
stored XOR dead-lettered, never silently gone:
- `tests/unit/relay/test_relay_dlq_invariant.py` (runs in the standard suite):
  drives a good/over-n_ctx mix through the **real** handler + `RelayService`
  (the embed 400 injected as `EmbedRequestError`) with fake writers + an in-process
  DLQ ledger; asserts `stored ⊎ dlq == published`, disjoint, with zero non-terminal naks.
- `tests/integration/test_relay_dlq_invariant.py` (`@pytest.mark.integration`,
  Docker): the same invariant against a **real pgvector store** — the stored ledger
  is read back from actual rows via `store.asearch`, proving no partial/silent write.
  The NATS transport is mocked (the integration harness provisions Postgres, not a
  JetStream broker); per-test UUID project namespaces isolate the row count.

The integration file was both adversarially reviewed (a 3-lens pass — API fidelity,
chunk/embed behavior, invariant/false-green — all three concluding it would pass,
with their robustness nits applied: per-test namespace, raw row-count assert,
explicit no-nak assert, sequential-ingest comment) **and then actually run against a
real ephemeral pgvector container — both tests pass**.

**Residual limitation (accurate scope):** what the pytest harness does *not* cover
is guard #2's max-deliver exhaustion over **live JetStream redelivery** —
`tests/integration/conftest.py` provisions only ephemeral Postgres, no NATS broker
(the live `ships-computer-nats` broker exists on the GB10 but is not wired into the
fixtures). That path is covered by the handler unit tests (delivery-count → DLQ+term)
and would need a persistent-transient failure staged against a live consumer to
exercise end-to-end. See memory `relay-deploy-and-test-reality`.
