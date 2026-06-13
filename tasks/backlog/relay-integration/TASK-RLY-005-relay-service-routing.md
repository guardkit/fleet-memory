---
id: TASK-RLY-005
title: RelayService.ingest - content_format routing and two-layer idempotency
task_type: feature
parent_review: TASK-REV-RLY04
feature_id: FEAT-MEM-04
wave: 3
implementation_mode: task-work
complexity: 7
dependencies:
  - TASK-RLY-001
  - TASK-RLY-002
  - TASK-RLY-003
  - TASK-RLY-004
tags:
  - routing
  - service
  - idempotency
  - relay
  - fleet-memory
consumer_context:
  - task: TASK-RLY-001
    consumes: MemoryEpisodeV1 / ContentFormat
    framework: Pydantic v2 envelope
    driver: pydantic>=2
    format_note: "Routes on episode.content_format; only json/markdown/text are recognized, anything else raises PoisonEpisodeError."
  - task: TASK-RLY-002
    consumes: PoisonEpisodeError / TransientIngestError
    framework: typed exceptions
    driver: stdlib
    format_note: "Raise PoisonEpisodeError(reason=...) for deterministic failures; let/raise TransientIngestError for recoverable ones. Unenumerated exceptions must propagate as transient."
  - task: TASK-RLY-003
    consumes: chunk_prose
    framework: pure function returning list[Chunk]
    driver: stdlib/pydantic
    format_note: "Call with target_tokens/overlap_ratio from Settings; empty result => zero chunks => success (ack)."
  - task: TASK-RLY-004
    consumes: ChunkWriter.write_chunks
    framework: async store writer
    driver: langgraph AsyncPostgresStore
    format_note: "write_chunks(episode_id, chunks) is idempotent via uuid5(episode_id, index)."
  - task: TASK-TPR-003
    consumes: PAYLOAD_REGISTRY / get_model_for_type
    framework: Pydantic v2 BasePayload dispatch
    driver: pydantic>=2
    format_note: "Unknown payload_type raises UnknownPayloadTypeError -> map to PoisonEpisodeError naming the type. No silent fallback."
  - task: TASK-DW-002
    consumes: DeterministicWriter.write
    framework: idempotent content-hash upsert
    driver: langgraph AsyncPostgresStore
    format_note: "Structured path builds a registered BasePayload then calls writer.write(); natural-key upsert makes redelivery inert (idempotency layer 1)."
---

# Task: RelayService.ingest - content_format routing and two-layer idempotency

## Description

The brain of the relay, with **zero NATS imports** (pure service — testable by
direct instantiation). `RelayService(writer, chunk_writer, settings)` exposes
`async def ingest(self, episode: MemoryEpisodeV1) -> None`.

Routing by `content_format`:
- **`json`** → resolve `payload_type` via `PAYLOAD_REGISTRY`, build & validate
  the typed `BasePayload`, call `DeterministicWriter.write()` (idempotency
  layer 1: natural-key upsert).
- **`markdown` / `text`** → `chunk_prose(...)` → `ChunkWriter.write_chunks(...)`
  (idempotency layer 2: episode_id-derived keys). Zero chunks (empty body) is a
  successful no-op.
- **anything else** → `PoisonEpisodeError("unrecognized content_format: ...")`.

Exception mapping (the correctness core):
- unparseable body, unknown payload type, payload validation failure,
  unrecognized format, hyphenated project (`NamespaceValidationError`),
  wrong-dimension embedding (`EmbedDimensionError`) → **`PoisonEpisodeError`**.
- embedding service/timeout/store unreachable (`EmbedTimeoutError`,
  `EmbedServiceError`, connection errors) → **`TransientIngestError`**.
- any unenumerated exception → propagate as transient (never poison).

`ingest` returns only after the durable write commits — its clean return is the
signal the handler (RLY-006) uses to ack. No language model is ever called.

## Acceptance Criteria

- [ ] `json` episodes dispatch through the registry to `DeterministicWriter.write`; a typed record exists in the project namespace
- [ ] `markdown` and `text` episodes are chunked and stored as chunks; same path for both
- [ ] Unknown `payload_type` raises `PoisonEpisodeError` naming the type; no record written
- [ ] A structured episode missing a required payload field raises `PoisonEpisodeError`; no record written
- [ ] `content_format` of `"yaml"` raises `PoisonEpisodeError`; no record or chunk created
- [ ] Hyphenated project raises `PoisonEpisodeError` on both paths; nothing written
- [ ] Embedding-service-unavailable raises `TransientIngestError` (NOT poison)
- [ ] Empty markdown body produces zero chunks and returns cleanly (success)
- [ ] Redelivery of an already-stored structured episode leaves exactly one record; redelivery of a chunked episode produces no duplicate chunks
- [ ] `ingest` makes zero language-model / chat-completion calls (assert via a no-network spy)
- [ ] The module imports nothing from `faststream` / NATS
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Seam Tests

```python
"""Seam test: verify exception taxonomy contract from TASK-RLY-002."""
import pytest

from fleet_memory.errors import PoisonEpisodeError, TransientIngestError


@pytest.mark.seam
@pytest.mark.integration_contract("exception_taxonomy")
async def test_unknown_format_is_poison(relay_service, make_episode):
    """Unrecognized content_format -> PoisonEpisodeError (DLQ), not transient.

    Contract: deterministic failure => PoisonEpisodeError; recoverable => TransientIngestError.
    Producer: TASK-RLY-002
    """
    with pytest.raises(PoisonEpisodeError):
        await relay_service.ingest(make_episode(content_format="yaml"))
```

## Coach Validation

```bash
pytest tests/unit/relay/test_service.py -v
ruff check src/fleet_memory/relay/service.py
python -c "import ast,sys; src=open('src/fleet_memory/relay/service.py').read(); assert 'faststream' not in src and 'import nats' not in src, 'service must not import NATS'"
```

## Implementation Notes

- Follow the handler/service separation rule: this service is constructed with
  its collaborators (writer, chunk_writer, settings) and never imports `broker`.
- Reuse `get_model_for_type` from `payloads/registry.py` and
  `DeterministicWriter` from `writer/core.py` unchanged.
- The zero-LLM assertion is a headline acceptance criterion — keep the write
  path free of any model/chat-completion client.
