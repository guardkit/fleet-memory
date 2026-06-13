---
id: TASK-DW-005
title: Supersession test suite
task_type: testing
parent_review: TASK-REV-DW03
feature_id: FEAT-MEM-03
wave: 4
implementation_mode: task-work
complexity: 4
dependencies:
- TASK-DW-003
tags:
- testing
- supersession
- retrieval
- fleet-memory
---

# Task: Supersession test suite

## Description

The second test suite the build plan calls for: the supersession behaviour of
TASK-DW-003. Unit tests run against a fake store (no infrastructure);
integration tests are marker-gated (`@pytest.mark.integration`) and run against
the ephemeral Postgres+pgvector fixture.

**Target files:**
- `tests/unit/test_writer_supersession.py`
- `tests/integration/test_writer_supersession.py`

Cover (from `deterministic-writer.feature`):

- Supersede-and-link: predecessor marked `superseded_by`, successor records the
  superseded key.
- Excluded-but-addressable: a superseded record is absent from default retrieval
  yet still retrievable directly by key.
- Supersession-count outline (0/1/5): every declared predecessor retired.
- Forward supersession (ASSUM-008): declaring a supersession of a not-yet-written
  key succeeds and is applied when that key later appears.
- Cross-project supersession: predecessor retired in another namespace; successor
  stays in its own.
- Idempotent re-declaration: predecessor stays superseded exactly once; no extra
  record.
- Chain A←B←C: only C in default retrieval; chain back to A traceable.
- Racing successors: exactly one recorded successor; no contradictory state.

## Acceptance Criteria

- [ ] Supersede-and-link and excluded-but-addressable cases pass.
- [ ] Supersession-count outline passes for {0, 1, 5}.
- [ ] Forward-supersession case passes: write succeeds, link applied when the key
      later appears (ASSUM-008).
- [ ] Cross-project supersession case passes.
- [ ] Idempotent re-declaration case passes (superseded exactly once, no extra
      record).
- [ ] Chain-collapse case passes: only C visible, chain to A traceable.
- [ ] Racing-successors case resolves to exactly one recorded successor.
- [ ] Unit tests pass with no infrastructure; integration tests are gated behind
      `@pytest.mark.integration` and pass against the ephemeral Postgres fixture.

## Coach Validation

```bash
pytest tests/unit -v -k "writer_supersession"
pytest tests/integration -m integration -k "writer_supersession" --timeout=120
```

## BDD scenarios covered

supersede-and-link, excluded-but-addressable, supersession-count outline,
forward supersession, cross-project supersession, idempotent re-declaration,
chain-collapse-traceable, racing successors.
