---
id: TASK-MEM-011
title: 'Integration tests: search boundaries and embed failures'
status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 7
implementation_mode: task-work
complexity: 5
estimated_minutes: 70
dependencies:
- TASK-MEM-010
tags:
- integration-tests
- boundaries
- negative-cases
consumer_context:
- task: TASK-MEM-004
  consumes: EPHEMERAL_PG_DSN
  framework: "pytest session fixture (ephemeral_pg) \u2014 seam owned by TASK-MEM-010"
  driver: docker compose + psycopg3
  format_note: Inherits the fixture contract proven by TASK-MEM-010's seam test; same
    conftest, no new seam stub required
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T22:09:07.320496'
  last_updated: '2026-06-12T22:19:08.311629'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T22:09:07.320496'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Integration tests — search boundaries and embed failures

## Description

Marker-gated integration tests for the boundary and negative scenarios: search
limit semantics (exactly-N, default cap), empty-store search, embed-service-down
atomicity (no partial writes), and hostile-content inertness. Uses the same
ephemeral fixture and store context as TASK-MEM-010.

## Acceptance Criteria

- [ ] Limit boundaries: with 15 relevant memories stored, `asearch(query, limit=N)` returns exactly N for N ∈ {1, 10, 15}, best-ranked first
- [ ] Default limit (ASSUM-002): `asearch(query)` with no limit returns at most 10 results — record the actual `AsyncPostgresStore` default; if it differs from 10, record the observed value for TASK-MEM-013 and assert the actual contract
- [ ] Empty store: `asearch("anything at all")` against a fresh namespace succeeds with zero results and no error
- [ ] Embed-down atomicity (ASSUM-005): with an injected always-failing embed callable, `aput` of a searchable memory raises an error identifying the embedding service AND a subsequent `aget` for that key returns nothing (no partial record); previously stored memories remain retrievable
- [ ] Hostile content: a memory containing SQL-injection-shaped text (e.g. `'; DROP TABLE memories; --`) round-trips byte-identical via `aput`/`aget`, appears normally in search, and no other memory or store structure is affected
- [ ] Dimension mismatch at the store boundary: a wrong-dims embed callable causes the write to fail with the dimension-mismatch error and leaves no partial record

## Test Requirements

- [ ] Files: `tests/integration/test_search_boundaries.py`, `test_embed_failures.py`, `test_injection_safety.py`
- [ ] All `@pytest.mark.integration`; excluded from the default run

## BDD Scenarios Covered

- "Search returns no more results than the requested limit" (all 3 outline rows)
- "Search without an explicit limit returns at most the default number of results"
- "Searching an empty store returns no results without error"
- "Storing a searchable memory fails cleanly when the embedding service is down"
- "Hostile memory content is stored verbatim and stays inert"

## Implementation Notes

- The failing-embed injection reuses `async_store_context(settings, embed_fn=failing_embed)` — no monkeypatching of internals
- Hostile-content equality must be byte-level (`stored == retrieved` on the raw value), not post-normalisation
- Fresh namespace per test for isolation within the session-scoped instance
