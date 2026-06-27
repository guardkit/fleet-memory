---
id: TASK-FIX-RELAYACKTMO01
title: Relay ack_wait (60s) + embed_timeout (10s) too tight for a shared/evicting embed server and large multi-chunk episodes — make ack_wait settings-driven, raise defaults
task_type: fix
status: in_review
created: 2026-06-27T00:00:00+00:00
updated: 2026-06-27T00:00:00+00:00
priority: high
tags:
  - relay
  - reliability
  - embed
  - ack-wait
  - harvest-incident
related:
  - TASK-FIX-RELAYDROP01
  - TASK-FIX-RELAYBATCH01
  - TASK-FIX-EMBEDCTX01
  - TASK-HARV-007
---

# Relay timeouts too tight for a contended embed server + large episodes

## Incident (2026-06-27, FEAT-HARV recovery)

Recovering the harvest (167 → 447 episodes) by replaying the intact MEMORY
stream through the rebuilt relay surfaced **two** ways the relay's timeouts are
too tight. Neither is the deterministic embed-400 that [[TASK-FIX-RELAYDROP01]]
fixed — both are *recoverable* failures the relay turned into DLQ entries or
infinite reprocessing:

1. **Embed cold-start vs `embed_timeout_s=10`.** The relay embeds against
   `embed` (Qwen3-Embedding-0.6B/1024) on the **shared** `:9000` llama-swap.
   When `embed` is evicted (by competing models — finproxy/granite-vision,
   forge, graphiti), the next request **cold-starts at 85–181s**. The 10s
   timeout killed every cold request; 5 deliveries all timed out →
   `max_deliver_exhausted` → DLQ (visible, not silently dropped, thanks to
   RELAYDROP01 — but a recoverable timeout should not DLQ). 15 episodes DLQ'd
   this way during the first recovery pass.
2. **Large multi-chunk episode vs `ack_wait=60`.** The relay embeds AND writes
   **every chunk** of an episode to the (NAS, over-Tailscale) Postgres before
   it acks. A 70+-chunk episode takes many minutes, so `ack_wait=60` expired
   mid-processing; JetStream redelivered it and the relay **reprocessed from
   scratch** — forever (observed: one episode monopolised the consumer for
   10+ minutes, `ack_pending=0`, re-emitting its whole chunk set, never
   committing).

`ack_wait` was **hardcoded** at 60s in `relay/handler.py` and `embed_timeout_s`
defaulted to 10s in `settings.py` — neither tunable for a deployment whose embed
server is shared/evicting and whose corpus has large documents.

## Root cause

- `embed_timeout_s` default (10s) < embed cold-start (85–181s).
- `ack_wait` (60s, hardcoded) < worst-case single-episode embed+commit time
  (large multi-chunk episode against remote Postgres).
- Invariant that was never enforced: **`ack_wait` MUST exceed `embed_timeout`**
  (else a single slow request triggers redelivery before it can finish) **and
  MUST exceed the largest episode's full embed+commit time** (else large
  episodes redeliver/reprocess forever).

This is the *absence-of-failure / tight-oracle* family again: a recoverable
slow path (cold-start, big episode) misclassified by a too-short deadline into
a hard failure (DLQ) or a non-terminating loop.

## Fix (ACTIONED 2026-06-27, working tree — pending commit)

1. **`ack_wait` is now settings-driven.** New `Settings.ack_wait_s`
   (`FLEET_MEMORY_ACK_WAIT_S`), default **1200s**. `relay/handler.py`'s
   `MEMORY_CONSUMER_CONFIG` reads `_ACK_WAIT_S = settings.ack_wait_s` instead of
   the hardcoded `60`.
2. **`embed_timeout_s` default raised 10 → 180** to absorb a cold-start in a
   single request (must stay `< ack_wait_s`).
3. **`max_deliver`** left settings-driven (default 5); with a correct `ack_wait`
   there is no mid-flight redelivery churn, so 5 is sufficient.

### Files changed

| File | Change |
|---|---|
| `src/fleet_memory/settings.py` | `embed_timeout_s` default `10.0 → 180.0`; new `ack_wait_s: int = 1200` field with the ack_wait > embed_timeout rationale |
| `src/fleet_memory/relay/handler.py` | `MEMORY_CONSUMER_CONFIG.ack_wait` `60 → _ACK_WAIT_S` (= `settings.ack_wait_s`, else 1200) |
| `tests/unit/test_settings.py` | default assertions updated (180.0 / 1200) + new `ack_wait_s > embed_timeout_s` invariant assertion |
| `deploy/relay/.env.deploy` | explicit `FLEET_MEMORY_EMBED_TIMEOUT_S=180`, `FLEET_MEMORY_ACK_WAIT_S=1200`, `FLEET_MEMORY_MAX_DELIVER=5` |

### Tests

`pytest tests/unit/relay tests/unit/test_settings.py tests/unit/test_embed.py`
→ **160 passed**. The two Docker integration DLQ-invariant tests still pass.

## Acceptance criteria

- [x] **AC-1** `ack_wait` is settings-driven (`FLEET_MEMORY_ACK_WAIT_S`), no
  longer hardcoded; default ≥ the largest observed episode's processing time.
- [x] **AC-2** `embed_timeout_s` default raised to cover a cold-start; the
  `ack_wait_s > embed_timeout_s` invariant is asserted in a test.
- [x] **AC-3** Live consumer recreated with `ack_wait=1200s`, DeliverAll;
  large episodes complete in one delivery (no redelivery loop).
- [x] **AC-4** Committed to main (2026-06-27); already live on the GB10 relay via
  `docker compose up -d --build`.

## Companion / dependency

The embed cold-start was *also* addressed at the infra layer by pinning
`embed` resident in the llama-swap fleet (dgx-spark
`TASK-LLSWAP-EMRESIDENT01`), so cold-starts are now rare. This task makes the
relay **robust by default regardless** — `embed` can still be evicted by the
exclusive llama-swap sets (`coach31`, `autobuild_go`, `coder_30b`), and other
deployments may have a busier embed server.

## Follow-ups (separate tasks, NOT in scope here)

- **Oversized-chunk truncation.** `chunk_target_tokens=1000` but the
  heading-aware chunker emits sections up to ~3000+ tokens, which RELAYBATCH01
  then **truncates** to the 2048-token embed budget → degraded embeddings for
  large sections. The chunker should hard-split sections to the embed budget.
- **Per-chunk commit / incremental ack.** The relay embeds+writes a whole
  episode before acking. Committing per-chunk (or in bounded batches) would cap
  the ack window need and let partial progress survive a restart — a better
  structural fix than a large `ack_wait`.
