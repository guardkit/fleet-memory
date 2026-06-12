---
id: TASK-MEM-003
title: Embed callable with dimension guard
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: feature
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 3
implementation_mode: task-work
complexity: 4
estimated_minutes: 45
dependencies: [TASK-MEM-002]
tags: [embeddings, httpx, nomic, timeout]
consumer_context:
  - task: TASK-MEM-002
    consumes: FLEET_MEMORY_SETTINGS
    framework: "httpx async client against OpenAI-compatible /v1/embeddings (llama-swap)"
    driver: "httpx"
    format_note: "embed_url is the base URL of the OpenAI-compatible API (e.g. http://gb10:9000/v1 or host root — normalise to .../v1/embeddings); embed_timeout_s is the httpx read-timeout bound in seconds (ASSUM-008 placeholder 10.0)"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Embed callable with dimension guard

## Description

Plain async httpx embed function against the OpenAI-compatible `/v1/embeddings`
endpoint served by llama-swap on GB10 (:9000). Signature:
`async def embed(texts: list[str], settings: Settings) -> list[list[float]]`
(or a `make_embed(settings)` factory returning the closed-over callable that
`AsyncPostgresStore` index config accepts). Post-call dimension validation: any
vector whose length differs from `settings.embed_dims` (768) raises
`EmbedDimensionError` — loud failure, never silent truncation. Timeout bounded by
`settings.embed_timeout_s` (ASSUM-008 default 10.0). Includes
`make_fake_embed(dims=768)` factory for the unit tier.

## Acceptance Criteria

- [ ] `python -m pytest tests/unit/test_embed.py -v` passes with zero network calls (httpx `MockTransport` throughout)
- [ ] Dimension-mismatch rows 512, 767, 769, 1024 each raise `EmbedDimensionError` whose message names both actual and expected dimensions (BDD `@boundary @negative` outline)
- [ ] A `MockTransport` that never responds triggers `EmbedTimeoutError` within `embed_timeout_s` — ASSUM-008 verification: record the actual httpx connect-vs-read timeout semantics observed, in a comment in `test_embed.py`
- [ ] `src/fleet_memory/embed.py` exports the async embed callable (settings-driven) and `make_fake_embed(dims=768)` returning a deterministic, network-free callable
- [ ] `src/fleet_memory/errors.py` exports `EmbedDimensionError`, `EmbedTimeoutError`, `EmbedServiceError`; error messages may name the embedding service URL but never any database credential
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_embed.py` — `MockTransport` only; no socket opened
- [ ] Failure-mode coverage: HTTP 500 → `EmbedServiceError`; malformed JSON → `EmbedServiceError`; timeout → `EmbedTimeoutError`; wrong dims → `EmbedDimensionError`

## BDD Scenarios Covered

- "An embedding of exactly 768 dimensions is stored and searchable" (callable side)
- "An embedding with the wrong number of dimensions is rejected" (all 4 outline rows)
- "A hung embedding service cannot stall store operations indefinitely"
- "Database credentials never appear in logs or error messages" (embed-side)

## Implementation Notes

- `httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=settings.embed_timeout_s, write=5.0, pool=5.0))` — the ASSUM-008 bound applies to the read phase (model inference time), confirm and record
- OpenAI-compatible request body: `{"model": settings.embed_model, "input": texts}`; response `data[i].embedding`
- The callable must be directly usable as the `embed` field of `AsyncPostgresStore` index config (TASK-MEM-005 consumes it) — keep the public shape `async (list[str]) -> list[list[float]]` via factory closure over settings
- Fake: `make_fake_embed(768)` returns deterministic unit-norm vectors derived from a text hash so ranking tests are stable
