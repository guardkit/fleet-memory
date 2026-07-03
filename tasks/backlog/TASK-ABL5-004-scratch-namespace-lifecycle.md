---
id: TASK-ABL5-004
title: Scratch namespace lifecycle for rollout-time writes
task_type: feature
parent_review: TASK-REV-ABL5
feature_id: FEAT-ABL-005
wave: 2
implementation_mode: task-work
complexity: 4
dependencies:
- TASK-ABL5-001
status: pending
tags:
- ablation
- fixture
- scratch-namespace
- fleet-memory
consumer_context:
- task: TASK-ABL5-001
  consumes: ScratchNamespaceError
  framework: fleet_memory.fixture.errors
  driver: Python exceptions
  format_note: Invalid rollout ids raise ScratchNamespaceError; messages credential-free
---

# Task: Scratch namespace lifecycle for rollout-time writes

## Description

`src/fleet_memory/fixture/scratch.py` — isolation for rollout-time writes
(scope §3.3: "fixture mounted read-only; rollout-time writes go to a scratch
namespace discarded per rollout").

Store namespaces are `("fleet_memory", <project>, <payload_type>)` tuples
persisted as dot-joined `prefix` text (e.g. `fleet_memory.guardkit.chunk`),
validated by `^[a-z0-9_]+$` per segment (`src/fleet_memory/store.py:26`).
Retrieval matches the project segment **exactly**
(`_matches_project`, `src/fleet_memory/retrieval/core.py:46-66`), so a
scratch **project** segment is invisible to corpus retrieval by construction
— that is the whole design.

API:

```python
SCRATCH_PREFIX = "scratch_"

def scratch_project(rollout_id: str) -> str
    # "scratch_<rollout_id>"; validates the result against ^[a-z0-9_]+$;
    # raises ScratchNamespaceError on empty/invalid ids (NO silent sanitising
    # — a mangled id would orphan the discard)

def scratch_namespace(rollout_id: str, payload_type: str) -> tuple[str, str, str]
    # ("fleet_memory", scratch_project(rollout_id), payload_type)

def discard_scratch(target_dsn, rollout_id: str) -> int
    # deletes every store row whose prefix equals
    # "fleet_memory.scratch_<id>" or starts with "fleet_memory.scratch_<id>."
    # (plus matching store_vectors rows, same transaction); returns rows
    # deleted; idempotent (0 on second call)

def list_scratch_projects(target_dsn) -> list[str]
    # distinct scratch_* project segments present in the store — lets the
    # rollout adapter assert "no scratch residue" before an arm starts
```

Guard rail: `discard_scratch` MUST refuse (ScratchNamespaceError) a
rollout_id that produces an invalid or empty project segment — a malformed
LIKE pattern must never be able to widen the delete beyond the scratch
project. The LIKE pattern must escape nothing implicitly: rollout ids are
validated to `[a-z0-9_]+` BEFORE pattern construction, and `_` in the id must
not act as a LIKE wildcard (escape it or match on the exact prefix segment
split).

Corpus safety invariant (tested): discarding a scratch namespace never
touches rows whose project segment is not the exact scratch project — in
particular a corpus project like `guardkit` and a sibling scratch project
`scratch_run2` survive `discard_scratch(dsn, "run1")` untouched.

## Acceptance Criteria

- [ ] `scratch_project("run_01")` == `"scratch_run_01"` and passes store namespace validation (`validate_namespace` accepts the tuple)
- [ ] Empty/invalid rollout ids (uppercase, hyphens, dots, path chars) raise `ScratchNamespaceError`; nothing is silently rewritten
- [ ] `discard_scratch` deletes only the exact scratch project's rows (prefix equal or prefix + `.`); `guardkit` rows and other `scratch_*` projects are untouched (unit test on generated SQL/pattern; integration proof in TASK-ABL5-006)
- [ ] `_` in rollout ids cannot act as a SQL LIKE wildcard (pattern escaped or segment-matched)
- [ ] `discard_scratch` removes matching `store_vectors` rows in the same transaction
- [ ] `discard_scratch` is idempotent (second call returns 0)
- [ ] `list_scratch_projects` returns only `scratch_*` project segments
- [ ] New code only under `src/fleet_memory/fixture/` (+ tests)
- [ ] All modified files pass project-configured lint/format checks with zero errors
- [ ] Unit tests green in the default suite (no Docker/Postgres — name validation and SQL/pattern construction tested pure)

## Test Requirements

Unit tests in `tests/unit/fixture/test_scratch.py`:
- name construction + validation matrix (valid, empty, uppercase, hyphen,
  dot, unicode)
- generated delete statements: exact-prefix + dotted-prefix match, LIKE
  wildcard escaping for `_`, parameterisation (no interpolation)
- idempotency + row-count return via fake connection seam
- `validate_namespace(("fleet_memory", scratch_project(x), "chunk"))` passes
  (imports the PUBLIC validator from `fleet_memory.store` — read-only use,
  no store code changes)

## Implementation Notes

- Writes themselves are performed by the rollout's own store client using
  `scratch_namespace(...)` — this module only names namespaces and discards
  them; it does not wrap `store.aput`.
- Prefer `prefix = %s OR prefix LIKE %s ESCAPE '\'` with the id's
  underscores escaped in the LIKE operand, or split-compare the second
  dot-segment; either satisfies the wildcard AC — test whichever is chosen.
