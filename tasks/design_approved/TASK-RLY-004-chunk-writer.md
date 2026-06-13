---
complexity: 6
consumer_context:
- consumes: Chunk
  driver: pydantic>=2
  format_note: Consumes list[Chunk]; writes each under namespace ('fleet_memory',
    project, 'chunk') with key uuid5(episode_id, str(index)).
  framework: Pydantic v2 frozen Chunk value object
  task: TASK-RLY-001
- consumes: AsyncPostgresStore record contract
  driver: langgraph-checkpoint-postgres>=2.0 (psycopg3)
  format_note: Stored value MUST carry a 'content' string field so the index config
    (fields=['content']) embeds it on write. Validate namespace with validate_namespace
    before any put.
  framework: langgraph AsyncPostgresStore via async_store_context (store.aput)
  task: TASK-MEM-005
dependencies:
- TASK-RLY-001
feature_id: FEAT-MEM-04
id: TASK-RLY-004
implementation_mode: task-work
parent_review: TASK-REV-RLY04
status: design_approved
tags:
- chunks
- storage
- idempotency
- relay
- fleet-memory
task_type: feature
title: Chunk writer - episode_id-derived ids, embed-on-write, idempotent storage
wave: 2
---

# Task: Chunk writer - episode_id-derived ids, embed-on-write, idempotent storage

## Description

`ChunkWriter.write_chunks(episode_id: str, chunks: list[Chunk]) -> None` in
`src/fleet_memory/relay/chunk_writer.py`. Persists prose chunks under
`("fleet_memory", project, "chunk")` via the existing `AsyncPostgresStore`
(embed-on-write through the store's index config — the same mechanism the
deterministic writer uses; no direct embed calls here).

**Idempotency layer 2 (the key contract):** each chunk's store key is
`uuid5(NAMESPACE_OID, f"{episode_id}:{chunk.index}")`. Redelivery of the same
episode overwrites the same keys in place → no duplicate chunks. This is what
makes the @regression "no duplicate chunks on redelivery" and the concurrency
"converges to a single outcome" scenarios pass by construction.

Each stored chunk value carries: `content` (the chunk text — required for
embed-on-write), `episode_id`, `chunk_index`, `source_ref`, `project`.

Validate the namespace with `validate_namespace` before any `aput` (rejects
hyphenated projects → caller turns the `NamespaceValidationError` into poison).

## Acceptance Criteria

- [ ] Chunk store key is `uuid5(episode_id, index)` — deterministic and stable across redeliveries
- [ ] Writing the same `(episode_id, chunks)` twice leaves an identical chunk set (no duplicates)
- [ ] Each stored value carries a `content` field so embed-on-write fires via the store index config
- [ ] Each stored chunk records `source_ref` and is confined to `("fleet_memory", project, "chunk")`
- [ ] `validate_namespace` is called before any `aput`; a hyphenated project raises `NamespaceValidationError` and writes nothing
- [ ] A delimiter/path-shaped `episode_id` cannot place a chunk outside the project's chunk namespace
- [ ] Unit tests use the in-memory/fake store + `make_fake_embed` (no live infra)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Seam Tests

The following seam test validates the integration contract with the store. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify chunk namespace + embed-on-write contract."""
import pytest

from fleet_memory.relay.schema import Chunk
from fleet_memory.relay.chunk_writer import ChunkWriter


@pytest.mark.seam
@pytest.mark.integration_contract("chunk_namespace")
async def test_chunk_written_under_project_chunk_namespace(fake_store):
    """Verify chunks land under ('fleet_memory', project, 'chunk') with content.

    Contract: namespace tuple + 'content' field for embed-on-write.
    Producer: TASK-RLY-001 (Chunk), TASK-MEM-005 (store)
    """
    writer = ChunkWriter(store=fake_store)
    chunks = [Chunk(index=0, text="hello", source_ref="ref://a", project="guardkit")]
    await writer.write_chunks("ep-1", chunks)
    stored = await fake_store.aget(("fleet_memory", "guardkit", "chunk"), ...)
    assert "content" in stored.value
```

## Coach Validation

```bash
pytest tests/unit/relay/test_chunk_writer.py -v
ruff check src/fleet_memory/relay/chunk_writer.py
```

## Implementation Notes

- Reuse the namespace+content pattern from
  `src/fleet_memory/writer/core.py::_write_record` (the `content` field is what
  the store embeds).
- Do NOT call `embed()` directly — embedding happens inside the store on `aput`
  via the index config wired in `async_store_context`.
- Partial-failure atomicity (low-confidence ASSUM): a mid-write failure should
  surface as a `TransientIngestError` so the episode is redelivered and the
  deterministic keys overwrite cleanly. Confirm intended behaviour via RLY-007.