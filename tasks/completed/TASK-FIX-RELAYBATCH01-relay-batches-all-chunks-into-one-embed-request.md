---
id: TASK-FIX-RELAYBATCH01
title: Relay embeds all of an episode's chunks in ONE batched request → exceeds embed n_ctx
task_type: fix
status: completed
created: 2026-06-26T00:00:00+00:00
updated: 2026-06-26T00:00:00+00:00
completed: 2026-06-26T00:00:00+00:00
previous_state: in_review
completed_location: tasks/completed/TASK-FIX-RELAYBATCH01-relay-batches-all-chunks-into-one-embed-request.md
priority: high
tags:
  - relay
  - embed
  - chunking
  - harvest-incident
related:
  - TASK-FIX-EMBEDCTX01
  - TASK-FIX-RELAYDROP01
---

# Relay batches all chunks of an episode into one embed request

## Incident (2026-06-26)

First live guardkit harvest stored 338/447 episodes; 109 multi-chunk episodes
silently dropped. `store` = `store_vectors` = 338 (1:1) — i.e. ONLY single-chunk
episodes survived; every multi-chunk episode failed.

## Root cause (this task's half)

The prose ingest path chunks correctly (`relay/service.py::_ingest_prose` →
`chunk_prose(target_tokens=chunk_target_tokens=1000, ...)`), producing ~1000-token
chunks. But the embed client sends them as a **single batched request**:

```python
# src/fleet_memory/embed.py
async def embed(texts: list[str], ...):
    request_body = {"model": ..., "input": texts}   # ALL chunks in one call
    response = await client.post(url, json=request_body)
```

llama.cpp `/v1/embeddings` caps the **batch's TOTAL tokens** at `n_ctx`
(currently 2048 — see [[TASK-FIX-EMBEDCTX01]]). So an episode that chunks into
N pieces sends ~N×1000 tokens in one request; once N×1000 > n_ctx the whole
request 400s, the episode never stores, and (because the 400 is mis-classified as
transient) it is silently dropped after `max_deliver` ([[TASK-FIX-RELAYDROP01]]).

Single-chunk episodes (≤ n_ctx) succeed — exactly the 338 that stored.

## Fix direction

Make the embed request size independent of episode size:

- Embed chunks in **sub-batches bounded by a token budget ≤ n_ctx** (greedy pack
  by estimated tokens), or per-chunk; never an unbounded single batch.
- Belt-and-suspenders with [[TASK-FIX-EMBEDCTX01]] (raise `n_ctx`) so the budget
  has headroom.
- Guard against a single chunk exceeding the budget (the heading-aware
  `chunk_prose` "never separates a heading from its section content", so a large
  non-splittable section can still exceed `target_tokens`) — hard-split or
  truncate-with-warning, and surface via the DLQ ([[TASK-FIX-RELAYDROP01]]), never
  a silent drop.

## Verification

Reproducer: an episode whose chunks sum to > n_ctx must store ALL its chunks
(N `store_vectors` rows, dim 1024) with nothing in the DLQ. Unit-test the
sub-batching token math against `n_ctx`.

## Recovery

`ChunkWriter` is idempotent (`uuid5(episode_id, index)`) → redelivering the 447
from the still-intact MEMORY stream after the fix is safe (no duplicates).

## Implementation (2026-06-26) — IN REVIEW

The fix lives entirely in the embed client (`embed()` is the single point where a
whole episode's chunk texts arrive in one call via the store's `real_embed`
delegate), so the blast radius is small: 2 source files + 1 test file.

- **`src/fleet_memory/settings.py`**: added `embed_max_batch_tokens` (default
  `2048`, `gt=0`). Per-request token budget; documented to stay ≤ the embed
  server's effective per-slot `n_ctx` (Qwen3-Embedding deploy = 8192/slot after
  [[TASK-FIX-EMBEDCTX01]]; nomic = 2048 hard) with headroom for estimation error.
- **`src/fleet_memory/embed.py`**:
  - `_estimate_tokens(text)` — conservative `ceil(len/4)` chars/token heuristic
    (min 1); the budget carries the headroom, so an approximate estimate is fine.
  - `_pack_batches(texts, budget)` — greedy packs inputs into ordered sub-batches
    each ≤ budget. A single input larger than the whole budget is **truncated to
    fit with a `WARNING`** (can't split one input into many vectors without
    breaking the 1-input→1-embedding contract; loud-but-degraded beats silent
    drop — true unembeddable inputs surface via the DLQ in [[TASK-FIX-RELAYDROP01]]).
  - `_embed_request(...)` — extracted the single-request POST + status/shape +
    per-vector dimension validation (unchanged semantics, now reusable per batch).
  - `embed()` — early-returns `[]` for empty input; otherwise sends one request
    **per sub-batch over a shared `AsyncClient`** and concatenates embeddings in
    input order. Request size is now independent of episode size;
    `len(result) == len(texts)` always.

### Verification

- New unit tests in `tests/unit/test_embed.py` pin the token math and the contract:
  `_estimate_tokens` heuristic; `_pack_batches` single/split/empty/oversized-truncate;
  and via `embed()` + `httpx.MockTransport` (counting requests) — single request
  under budget, the **reproducer** (4 chunks summing > budget → 2 requests, ALL
  chunks embedded in order), oversized-chunk truncate-then-embed, and empty→no-request.
- Full unit suite: **483 passed, 3 deselected (integration), 0 failures**.
- `ruff check` on all changed files: clean.

### Notes / follow-ups

- Defaults `embed_model`/`embed_dims` left as-is (nomic/768) — the Qwen/1024 switch
  is the separate qwen-embed-switch work, and this fix is model-agnostic.
- The end-to-end reproducer from the spec (real over-`n_ctx` episode → N
  `store_vectors` rows, nothing in DLQ) requires a live broker + embed server; it is
  covered structurally by the unit reproducer here and belongs to the integration
  suite. Recovery replay of the 447 is safe once this + [[TASK-FIX-RELAYDROP01]] land.
- Coverage tool is not installed in the local `.venv`; every new branch is
  exercised by the added tests.
