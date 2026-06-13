---
id: TASK-RIP-010
title: Integration tests — idempotency, concurrency, resilience, injection
status: backlog
created: 2026-06-13 20:30:00+00:00
updated: 2026-06-13 20:30:00+00:00
priority: high
task_type: testing
parent_review: TASK-REV-RIP7
feature_id: FEAT-MEM-07
wave: 7
implementation_mode: task-work
complexity: 6
estimated_minutes: 90
dependencies:
- TASK-RIP-006
- TASK-RIP-007
- TASK-RIP-008
- TASK-RIP-009
tags:
- reindex
- integration
- idempotency
- concurrency
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Integration tests — idempotency, concurrency, resilience, injection

## Description

Marker-gated integration tests exercising the full publish → relay → writer →
store path against an **ephemeral Postgres + pgvector** instance (hermetic — no
NAS dependency, per the FEAT-MEM-01 test topology). These prove the
downstream-idempotency and resilience guarantees that unit tests with a fake
publisher cannot: the second run is a no-op, an edit re-indexes as an update,
concurrent runs converge, double-publish dedups, injection content round-trips
inert, and reviewed backfill stores like a parsed payload.

## Acceptance Criteria

- [ ] A second run over an unchanged corpus creates or modifies no stored record
- [ ] Re-indexing after editing a source document updates its record to the new content with no duplicate record
- [ ] Two re-index runs started at the same time converge to exactly one record per natural key (no duplicate from the overlapping runs)
- [ ] Publishing the same parsed document twice yields exactly one record for its natural key
- [ ] A document whose body contains injection-shaped text is stored byte-for-byte and no command executes during ingest
- [ ] A reviewed backfill payload is stored as a typed record like a deterministically parsed payload
- [ ] All tests are `@pytest.mark.integration` gated and run against an ephemeral pgvector instance (excluded from the default hermetic unit run)

## Test Requirements

- [ ] `tests/integration/reindex/test_idempotency.py::test_second_run_is_noop`
- [ ] `tests/integration/reindex/test_idempotency.py::test_edit_updates_not_duplicates`
- [ ] `tests/integration/reindex/test_concurrency.py::test_concurrent_runs_converge`
- [ ] `tests/integration/reindex/test_idempotency.py::test_double_publish_single_record`
- [ ] `tests/integration/reindex/test_security.py::test_injection_body_stored_verbatim`
- [ ] `tests/integration/reindex/test_backfill.py::test_reviewed_backfill_stored_as_typed_record`

## BDD Scenarios Covered

- "A second run over an unchanged corpus leaves the store unchanged"
- "Re-indexing after editing a source document updates its record rather than duplicating it"
- "Two re-index runs started at the same time converge to a single stored outcome"
- "Publishing the same parsed document twice yields a single stored record"
- "A document whose body contains injection-shaped text is published verbatim and stays inert" (store side)
- "Reviewed backfill payloads publish through the same relay path as deterministically parsed documents" (store side)

## Implementation Notes

- Use the `deploy/local/` ephemeral compose + random-port idiom from FEAT-MEM-01 so
  parallel worktrees never share state. Real embeddings via llama-swap `:9000` or a
  fake embed fn where vectors are not under test.
- The interrupted-run / outage scenario's *unit* coverage lives in TASK-RIP-009;
  here, assert the post-recovery store invariant (exactly one record per key).
