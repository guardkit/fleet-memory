---
id: TASK-ABL5-003
title: Per-task temporal-cut filter on episode_meta.occurred_at
task_type: feature
parent_review: TASK-REV-ABL5
feature_id: FEAT-ABL-005
wave: 2
implementation_mode: task-work
complexity: 5
dependencies:
- TASK-ABL5-001
status: pending
tags:
- ablation
- fixture
- temporal-cut
- leakage-control
- fleet-memory
consumer_context:
- task: TASK-ABL5-001
  consumes: InvalidCutDateError + FixtureError taxonomy
  framework: fleet_memory.fixture.errors
  driver: Python exceptions
  format_note: Invalid/missing cut dates raise InvalidCutDateError; all messages credential-free
---

# Task: Per-task temporal-cut filter on episode_meta.occurred_at

## Description

`src/fleet_memory/fixture/temporal_cut.py` — the answer-key leakage control
(scope §3.3). For an eval task with a FEAT start date, remove from a restored
**per-run** store every entry the on-arm must not see:

1. entries whose `episode_meta.occurred_at` is **on or after** the task's
   FEAT start date (`>=` — the boundary instant itself is excluded), AND
2. **every** entry whose `episode_meta.occurred_at` is NULL or absent
   (distilled build_outcomes/ADRs reference MEM08-era work — answer-key
   risk; 176 such entries on the live store, verified 2026-07-03).

**The cut axis is `value->'episode_meta'->>'occurred_at'` — NEVER the row
`created_at` column**, which is backfill-era (2026-06-28 onward) and useless:
an entry ingested during the backfill but describing 2026-05 work MUST
survive a 2026-06-25 cut.

API:

```python
@dataclass(frozen=True)
class CutResult:
    excluded_after_cut: int   # occurred_at >= cut instant
    excluded_null: int        # occurred_at NULL/absent
    remaining: int            # store rows left after the cut

def apply_temporal_cut(target_dsn, cut, *, dry_run=False) -> CutResult
```

- `cut` accepts a `datetime.date` (interpreted as midnight UTC at the start
  of that date), a timezone-aware `datetime`, or an ISO-8601 string parsing
  to one of those. Anything else (including `None`, empty string, naive
  datetime, garbage text) raises `InvalidCutDateError` — a cut that silently
  skips leakage control is worse than no cut.
- The session runs with `SET TIME ZONE 'UTC'`; the SQL comparison casts the
  stored ISO string: `(value #>> '{episode_meta,occurred_at}')::timestamptz >= %(cut)s`.
  The NULL branch (`(value #>> '{episode_meta,occurred_at}') IS NULL`) covers
  JSON null, absent `occurred_at` key, and absent `episode_meta` entirely.
- Deletion is transactional and covers the search index: after the cut, no
  `store_vectors` row may reference a deleted `store` row (rely on the FK
  ON DELETE CASCADE if present in the langgraph schema — verify — otherwise
  delete vectors explicitly in the same transaction).
- **Idempotent**: re-applying the same cut returns
  `CutResult(0, 0, remaining)` and changes nothing.
- `dry_run=True` computes the counts without deleting (used by the CLI for
  operator preview and by validation to check the 176 on fixture v1).
- This module NEVER runs against the live store by design of its callers;
  nothing in it should ever construct a DSN itself — it acts on the DSN it
  is given (a restored per-run store).

## Acceptance Criteria

- [ ] Cut predicate uses `episode_meta.occurred_at` exclusively; the SQL contains no reference to the `created_at` column (unit-test the generated SQL)
- [ ] Boundary semantics: `occurred_at` exactly equal to the cut instant is excluded; one second before is retained (unit test on predicate construction + integration proof in TASK-ABL5-006)
- [ ] NULL/absent `occurred_at` (JSON null, missing key, missing `episode_meta`) is always excluded, and counted separately in `CutResult.excluded_null`
- [ ] A `date` cut means midnight UTC of that date; naive datetimes are rejected with `InvalidCutDateError`
- [ ] `None`/empty/garbage cut values raise `InvalidCutDateError` and the store is untouched
- [ ] Re-applying the same cut is a no-op reporting zero exclusions
- [ ] `dry_run=True` never deletes
- [ ] Deletion removes matching search-index (`store_vectors`) rows in the same transaction (no orphans)
- [ ] New code only under `src/fleet_memory/fixture/` (+ tests)
- [ ] All modified files pass project-configured lint/format checks with zero errors
- [ ] Unit tests green in the default suite (no Docker/Postgres — SQL/predicate construction and cut-value parsing tested pure; live-schema behaviour lands in TASK-ABL5-006)

## Test Requirements

Unit tests in `tests/unit/fixture/test_temporal_cut.py`:
- cut-value normalisation: date -> midnight UTC; aware datetime passthrough;
  ISO strings; rejection of naive datetime / None / empty / garbage
- SQL construction: predicate targets `episode_meta.occurred_at` path, `>=`
  comparison, parameterised cut value (no string interpolation), no
  `created_at` reference
- dry-run does not emit DELETE (fake connection seam records statements)
- CutResult arithmetic from fake execution results

Seeded-store behaviour (the FEAT-HARV / OUT-SMOKE / 176-null acceptance
proof) is TASK-ABL5-006's integration suite.

## Implementation Notes

- `#>>` (path extraction) is the right operator: `value->'episode_meta'->>'occurred_at'`
  and `value #>> '{episode_meta,occurred_at}'` are equivalent; use one form
  consistently and unit-test it.
- Follow the credential-hygiene rule: errors name host:port/db only.
- Keep a small injectable connection factory so unit tests can drive the
  module without Postgres.
