---
complexity: 4
dependencies:
- TASK-DW-002
feature_id: FEAT-MEM-03
id: TASK-DW-004
implementation_mode: task-work
parent_review: TASK-REV-DW03
status: design_approved
tags:
- testing
- idempotency
- zero-llm
- integrity
- fleet-memory
task_type: testing
title: Idempotency and zero-LLM test suite
wave: 3
---

# Task: Idempotency and zero-LLM test suite

## Description

The first of the two test suites the build plan calls for, plus the zero-LLM
acceptance criterion expressed as an enforceable negative. Unit tests run against
a fake store/embed (no infrastructure); integration tests are marker-gated
(`@pytest.mark.integration`, deselected by default) and run against the ephemeral
Postgres+pgvector fixture in `tests/integration/conftest.py`.

**Target files:**
- `tests/unit/test_writer_idempotency.py`
- `tests/unit/test_writer_zero_llm.py`
- `tests/integration/test_writer_idempotency.py`

Cover (from `deterministic-writer.feature`):

- **Idempotency**: identical content twice → one record, unchanged, no re-embed;
  byte-identical boundary → no new version; single-character difference → version
  advances by one; batch outline (0/1/50) → one record per distinct key;
  re-running a full corpus a second time creates no new records and changes none.
- **Concurrency/integrity**: concurrent duplicate writes of the same payload
  converge to exactly one record (at-least-once delivery); a write interrupted
  after embed but before commit leaves no observable partial record and the retry
  yields exactly one complete record; a read during a concurrent versioned write
  only ever sees a complete old or complete new version.
- **Failure modes**: embedding-unavailable, embedding-dimension-mismatch, and
  database-unreachable each fail the whole write with no partial record and a
  diagnostic naming the failing target.
- **Validation/security negatives**: hyphenated project rejected before any
  write; non-registered input rejected; hostile content (DB commands /
  injection-shaped text) written byte-for-byte and read back inert with no other
  record or store structure affected; delimiter/path-shaped text in an identifier
  field rejected with the underscores-only error (cannot forge a different
  identity).
- **Zero-LLM negative import test**: assert that no code path reachable from the
  writer can construct a language-model client — scan the writer package's
  imports and assert the absence of any LLM client symbol; constructing the
  writer and exercising a write touches no LLM module.

## Acceptance Criteria

- [ ] Idempotency cases pass: identical-content no-op (no re-embed),
      byte-identical no-version, single-character new-version, batch outline
      (0/1/50), full-corpus re-run no-change.
- [ ] Concurrency cases pass: concurrent duplicate convergence to one record,
      interrupted-write atomicity on retry, read-during-versioned-write sees only
      complete versions.
- [ ] Failure-mode cases pass: embed-unavailable, dimension-mismatch, and
      db-unreachable each leave no partial record and name the failing target.
- [ ] Negative cases pass: hyphen-namespace reject, not-a-payload reject,
      hostile-content inert round-trip, delimiter-forge-identity reject.
- [ ] The zero-LLM negative test fails if any LLM client import/construction is
      added to the writer path, and passes for the current writer.
- [ ] Unit tests pass with no infrastructure; integration tests are gated behind
      `@pytest.mark.integration` and pass against the ephemeral Postgres fixture.

## Coach Validation

```bash
pytest tests/unit -v -k "writer and (idempoten or zero_llm or integrity)"
pytest tests/integration -m integration -k "writer_idempotency" --timeout=120
```

## BDD scenarios covered

identical-content no-op, byte-identical boundary, single-character boundary,
batch outline, full-corpus re-run, concurrent duplicate convergence,
interrupted-write atomicity, read-during-versioned-write, embed-unavailable,
dimension-mismatch, db-unreachable, hyphen-namespace reject, not-a-payload
reject, hostile-content inert, delimiter-forge-identity reject, zero-LLM
negative import.