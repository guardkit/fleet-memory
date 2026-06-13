---
id: TASK-MEM-009
title: Unit test suite completion (hermetic tier)
status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 6
implementation_mode: task-work
complexity: 4
estimated_minutes: 60
dependencies:
- TASK-MEM-003
- TASK-MEM-005
- TASK-MEM-006
tags:
- unit-tests
- hermetic
- credential-hygiene
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T21:13:01.275659'
  last_updated: '2026-06-12T21:25:31.908230'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T21:13:01.275659'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Unit test suite completion (hermetic tier)

## Description

Complete the network-free, database-free unit tier. Earlier tasks created focused
test stubs (`test_embed.py`, `test_store_validation.py`, `test_app_lifespan.py`,
`test_settings.py`); this task expands them into the full hermetic suite and adds
`test_credential_hygiene.py`. The tier's contract: `FLEET_MEMORY_PG_DSN` and
`FLEET_MEMORY_EMBED_URL` are NOT set in the environment, no socket is opened, and
the whole tier finishes in seconds — proving the BDD scenario "Unit tests pass
with no database and no embedding service available".

## Acceptance Criteria

- [ ] `python -m pytest tests/unit/ -v --timeout=30` passes with `FLEET_MEMORY_PG_DSN` and `FLEET_MEMORY_EMBED_URL` unset (hermetic by construction)
- [ ] `test_credential_hygiene.py`: when the embed callable raises `EmbedServiceError` and when `async_store_context` fails on a bad DSN, no propagated message contains the password component of the DSN
- [ ] Settings `ValidationError` from empty env names the missing `pg_dsn` / `embed_url` fields (message includes each missing setting's name)
- [ ] Suite covers: settings defaults + precedence, namespace hyphen rejection, all four dimension-mismatch rows, embed timeout, fake-embed store-factory construction, lifespan enter/exit with stubs
- [ ] Total wall-clock for `python -m pytest tests/unit/ -q` is under 10 seconds (network-free proof — no blocking call hides in the tier)
- [ ] Tests do not import psycopg directly and never call `async_store_context().__aenter__` against a real DSN

## Test Requirements

- [ ] All unit tests pass; the tier alone satisfies the default `pytest` invocation (integration excluded by marker)

## BDD Scenarios Covered

- "Unit tests pass with no database and no embedding service available"
- "Missing required settings prevent startup with a clear message"
- "Database credentials never appear in logs or error messages"
- "A namespace containing hyphens is rejected"
- "An embedding with the wrong number of dimensions is rejected"
- "A hung embedding service cannot stall store operations indefinitely"

## Implementation Notes

- Use `monkeypatch.delenv` to guarantee env emptiness regardless of the developer's shell
- Credential-hygiene assertion helper: extract the password from the test DSN, assert `password not in str(exc)` across every captured failure path
- Keep per-test fixtures function-scoped; the tier must stay order-independent
