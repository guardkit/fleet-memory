---
complexity: 6
consumer_context:
- consumes: Chunk / MemoryEpisodeV1
  driver: pydantic>=2
  format_note: Chunker returns list[Chunk] with monotonic index starting at 0; each
    Chunk carries text, index, source_ref, project. Empty/whitespace body returns
    [].
  framework: Pydantic v2 value objects (frozen Chunk model)
  task: TASK-RLY-001
dependencies:
- TASK-RLY-001
feature_id: FEAT-MEM-04
id: TASK-RLY-003
implementation_mode: task-work
parent_review: TASK-REV-RLY04
status: design_approved
tags:
- chunking
- prose
- relay
- fleet-memory
task_type: feature
title: Heading-aware prose chunker with size and overlap
wave: 2
---

# Task: Heading-aware prose chunker with size and overlap

## Description

Pure, network-free function `chunk_prose(body: str, *, target_tokens: int,
overlap_ratio: float, source_ref, project) -> list[Chunk]` in
`src/fleet_memory/relay/chunker.py`. Splits markdown/text into heading-aware
chunks for the prose write path. No store, no embedding, no NATS — just text in,
`Chunk` list out, so the dense boundary scenarios are unit-testable.

Behaviour (from the @boundary scenarios):
- Body **well under** one chunk → 1 chunk; **exactly** one chunk → 1 chunk;
  **just over** → 2 chunks; **several chunks long** → multiple.
- Adjacent chunks **overlap** by ~`overlap_ratio` of chunk size so meaning is
  not severed at a cut.
- Boundaries **prefer heading breaks** over splitting mid-section; a heading
  line is never separated from the section it introduces.
- **Empty or whitespace-only** body → returns `[]` (zero chunks) — the episode
  is later acknowledged, not parked (low-confidence ASSUM; confirm via RLY-007).

`target_tokens` (~1000, OD-1) and `overlap_ratio` (~0.15, OD-1) are parameters,
sourced from Settings by the caller — do not hardcode.

## Acceptance Criteria

- [ ] Body under target size produces exactly 1 chunk
- [ ] Body just over target size produces 2 chunks with overlapping content between them
- [ ] A multi-heading document splits at heading boundaries where possible; no heading is orphaned from its section
- [ ] Each chunk after the first begins with content overlapping the previous chunk
- [ ] Empty body and whitespace-only body both return `[]`
- [ ] `Chunk.index` is monotonic from 0; `source_ref` and `project` propagate to every chunk
- [ ] Function is pure: no I/O, deterministic for a given input
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Seam Tests

The following seam test validates the integration contract with the producer task. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify Chunk contract from TASK-RLY-001."""
import pytest

from fleet_memory.relay.chunker import chunk_prose


@pytest.mark.seam
@pytest.mark.integration_contract("Chunk")
def test_chunk_contract_shape():
    """Verify chunk_prose returns Chunk objects matching the RLY-001 contract.

    Contract: list[Chunk] with monotonic index from 0; empty body -> [].
    Producer: TASK-RLY-001
    """
    chunks = chunk_prose("# H\nsome body text", target_tokens=1000,
                         overlap_ratio=0.15, source_ref="ref://x", project="guardkit")
    assert all(c.project == "guardkit" for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunk_prose("   ", target_tokens=1000, overlap_ratio=0.15,
                      source_ref=None, project="guardkit") == []
```

## Coach Validation

```bash
pytest tests/unit/relay/test_chunker.py -v
ruff check src/fleet_memory/relay/chunker.py
```

## Implementation Notes

- Token counting can be approximate (whitespace/heuristic) for v1 — the OD-1
  values are starting points, not contractual.
- Keep heading detection markdown-aware (`#`..`######`); plain text with no
  headings falls back to size-based splitting on paragraph boundaries.