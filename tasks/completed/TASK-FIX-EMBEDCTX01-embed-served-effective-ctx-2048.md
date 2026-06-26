---
id: TASK-FIX-EMBEDCTX01
title: Embed served at effective 2048 tok/slot (ctx 8192 ÷ np 4) — too small for ingest batches
task_type: fix
status: completed
created: 2026-06-26T00:00:00+00:00
updated: 2026-06-26T00:00:00+00:00
completed: 2026-06-26T00:00:00+00:00
priority: high
tags:
  - embed
  - llama-swap
  - qwen-embed-switch
  - harvest-incident
related:
  - TASK-FIX-RELAYBATCH01
  - TASK-FIX-RELAYDROP01
---

# Embed served at effective 2048 tok/slot

## Resolution (2026-06-26) — COMPLETE (applied live + canonical, verified on-box)

The agent was **running on `promaxgb10-41b1` itself**, so the live deploy was done
directly (the earlier SSH failure was just unkeyed self-SSH; the box's filesystem
and `:9000` are local).

**Change applied (both places):** the `embed` (Qwen3-Embedding-0.6B) block,
`--ctx-size 8192` → **`--ctx-size 32768`** (kept `-np 4`, `--batch-size 8192`,
`--ubatch-size 8192`). Effective per-slot ctx: **2048 → 8192 tokens** (32768 ÷ 4).

- **Live:** `/opt/llama-swap/config/config.yaml` on the box. Backup taken first
  (`~/config.live.bak.embedctx01.20260626-155444`). `-watch-config` auto-reloaded;
  diff vs backup is **exactly one line** (the embed `--ctx-size`).
- **Canonical:** `dgx-spark/examples/llama-swap-config.public.yaml` (the config the
  bring-up runbook deploys). Block comment rewritten to encode the `n_ctx ÷ np`
  gotcha so it is not reintroduced.

**Verified on-box (isolated from the running fleet).** A throwaway `llama-server`
with the exact new args proved the per-slot allocation and the ceiling shift:
- server log: `new slot, n_ctx = 8192` ×4 (i.e. `--ctx-size 32768 -np 4` ⇒ 8192/slot;
  `n_ctx_seq 8192 < n_ctx_train 32768` ⇒ no rope scaling — Qwen3-Embedding is a 32K model).
- 2 390-tok input → **HTTP 200, dim 1024** (was 400 at 2048/slot).
- 7 170-tok input → **HTTP 200, dim 1024**.
- 23 890-tok input → **HTTP 400, n_ctx=8192** (correctly capped at the new ceiling —
  that is RELAYBATCH01's domain, see below).
The live `embed` model was also observed serving 200s at `--ctx-size 32768` and
passing its health check in the llama-swap log.

**Value choice — `-np 4` (8192/slot), not `-np 1` (32768/slot).** `-np 4` keeps
`--ubatch-size 8192` unchanged ⇒ memory profile identical to the proven config;
`-np 1 → 32768/slot` would need `--ubatch-size 32768`, whose non-flash O(n²)
attention buffer is tens of GB (OOM risk). The task's own steer is that the relay
sub-batching ≤ n_ctx ([[TASK-FIX-RELAYBATCH01]]) is the cleaner lever, so a huge
per-slot ctx is not needed.

### nomic-embed audit — finding: NOT the same cliff; left unchanged

The task flagged the live `nomic-embed` block (also `--ctx-size 8192 -np 4`) for the
same audit. **Standalone testing showed it is NOT fixable by bumping `--ctx-size`:**
`nomic-embed-text-v1.5`'s GGUF reports **`n_ctx_train = 2048`**, and llama.cpp
**clamps** per-slot ctx to that — launching it with `--ctx-size 32768 -np 4` still
allocated `new slot, n_ctx = 2048`, and a 2 550-tok input still returned
`HTTP 400 n_ctx=2048`. So nomic's 2048 ceiling is a **hard model limit**, not an
`-np`-division artifact like Qwen's was. Setting it to 32768 would be ineffective
**and** misleading. **`nomic-embed` was therefore left at `--ctx-size 8192`** (already
at its model max). Consumers (graphiti-mcp / forge) must chunk ≤2048, or enable yarn
rope-scaling at an embedding-quality risk. The canonical config comment was corrected
to record this asymmetry.

### Separate pre-existing issue discovered (NOT this task) — eviction thrash

While on the box, found a **pre-existing** eviction-thrash (first granite-vision
proxy-reset 15:47:56, ~10 min **before** this edit at 15:58 — not caused by it):
the `finproxy-api` container (`172.21.0.4`) requests `granite-vision-4-1-4b` in a
tight loop. `granite-vision` lives in the **exclusive `lpa` matrix set** (evicts the
`all` family); `qwen-graphiti` + `coach-ft-v3` + `embed` live in `all`. With forge
(`coach-ft-v3`) and graphiti (`qwen-graphiti`/`nomic-embed`) active, the two sets
conflict permanently, so `finproxy-api` can never hold `granite-vision` and
retry-loops (456 connection-resets logged), spamming the llama-swap log. This is a
matrix-sets / capacity-or-client issue, **out of scope for EMBEDCTX01** — flagged to
the operator for a decision (fix the finproxy client loop, or rework the `lpa`/`all`
set capacity). Critical services were healthy throughout (nomic served graphiti at
200/56 ms; the `all` family stayed loaded).

### What remains (other tasks — NOT this one)

EMBEDCTX01 (the embed serving size) is done. Full recovery of the 109 dropped
episodes is gated on the other two fixes:
- [[TASK-FIX-RELAYBATCH01]] — relay must sub-batch each `/v1/embeddings` request
  ≤ n_ctx (8192) so whole-episode batches >8192 tok stop 400-ing.
- [[TASK-FIX-RELAYDROP01]] — a residual deterministic 400 must go to the DLQ, not be
  silently dropped.
Then redeliver the durable consumer over the intact MEMORY stream (447, seq 19–465);
`ChunkWriter` is idempotent (`uuid5`), so replay is safe.

---

## Incident (2026-06-26)

First live guardkit harvest after the nomic→Qwen/1024 embedder switch landed only
**338 of 447 episodes**. The 109 missing were not in the DLQ (DLQ empty) and the
JetStream consumer had drained (`Ack Pending: 0, Unprocessed: 0`) — they were
**silently dropped** (see [[TASK-FIX-RELAYDROP01]]).

## Root cause (this task's half)

The `embed` model (Qwen3-Embedding-0.6B) is served on llama-swap `:9000` with:

```
--ctx-size 8192   -np 4
```

llama.cpp divides the context across the parallel slots, so the **effective
context is 8192 ÷ 4 = 2048 tokens per slot**. Any `/v1/embeddings` request whose
input exceeds 2048 tokens returns HTTP 400:

```json
{"code":400,"type":"exceed_context_size_error",
 "message":"request (12002 tokens) exceeds the available context size (2048 tokens)...",
 "n_ctx":2048}
```

(Reproduced live both at incident time and again 2026-06-26 pre-fix: a 23 890-token
input → 400 n_ctx=2048; a short input → 200/1024.)

## Why it bites

The relay batches all of an episode's chunks into ONE embeddings request
([[TASK-FIX-RELAYBATCH01]]), so the per-request token total is the SUM of an
episode's chunks. Multi-chunk episodes (total > 2048 tokens) 400. Only
single-chunk/small episodes (≤2048 total) stored — hence `store` = `store_vectors`
= 338 exactly (1:1).

## Fix direction (as applied)

`--ctx-size 32768 -np 4` → 8192/slot (kept ubatch 8192). See the Resolution above
for the `-np 4`-vs-`-np 1` rationale and the on-box verification. Coordinate with the
relay-side per-request budget ([[TASK-FIX-RELAYBATCH01]]): the cleaner fix is the
relay embedding in sub-batches ≤ n_ctx, so the ctx need not absorb a whole large
episode at once.

> ⚠️ The live `nomic-embed` block has the same `--ctx-size 8192 -np 4` shape but a
> DIFFERENT cause — it is hard-capped at `n_ctx_train=2048` and is NOT fixable by
> `--ctx-size` (see the nomic-embed audit in the Resolution). Left unchanged.

## Recovery (after all three fixes)

The MEMORY stream still holds all 447 (seq 19–465). `ChunkWriter` is idempotent
(`uuid5(episode_id, index)`), so recreating/redelivering the durable consumer
re-reads all 447 safely: the 338 re-upsert harmlessly, the 109 now embed. Verify
`store`/`store_vectors` reach the full set and the DLQ stays empty. Gated on
EMBEDCTX01 (done) + RELAYBATCH01 + RELAYDROP01.

## Notes

The guardkit harvest itself is correct (it publishes full episodes; chunking +
embedding are the relay's job). No guardkit code change needed. See the agent
memory note `qwen-embed-switch-1024`.
