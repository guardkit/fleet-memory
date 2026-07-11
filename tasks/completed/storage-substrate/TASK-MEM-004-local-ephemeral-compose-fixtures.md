---
id: TASK-MEM-004
title: Local ephemeral compose and pytest fixtures
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-CA81 completed"
pre_sweep_status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: infrastructure
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 2
implementation_mode: task-work
complexity: 5
estimated_minutes: 60
dependencies:
- TASK-MEM-001
tags:
- docker-compose
- pgvector
- hermetic-testing
- fixtures
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 3
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T18:52:05.398237'
  last_updated: '2026-06-12T19:22:22.361465'
  turns:
  - turn: 1
    decision: feedback
    feedback: '- Gathering status is ''partial_honesty_abort'' - evidence collection
      aborted before independent test verification could run. All verification fields
      (independent_tests, tests, coverage_details, bdd, arch_review, quality_gates)
      are null.: The orchestrator aborted evidence gathering due to honesty issues.
      Player must not claim files in completion_promises.implementation_files that
      were not modified in the current turn. Use files_authored to track delegation
      outputs, not files_modified/files_created.

      - Honesty verification shows 6 ''should_fix'' discrepancies: Player claimed
      files (deploy/local/docker-compose.yml, deploy/local/initdb/01_extensions.sql,
      tests/conftest.py, tests/integration/conftest.py, tests/integration/test_ephemeral_fixture.py,
      tests/unit/test_fake_embed_fixture.py) that are tracked in git but show no changes
      in ''git status --porcelain'' for this turn.: When delegating to task-work,
      do not sweep delegated outputs into files_modified/files_created. Report files_modified:
      [] and files_created: [] accurately for the Player''s own work. Reference delegated
      files only via files_authored or in completion_promises.evidence with clear
      attribution to the delegated agent.

      - No independent test verification available - cannot confirm Player''s claim
      of 5 passing tests. The ''tests'', ''independent_tests'', and ''coverage_details''
      fields are all null due to gathering abort.: Fix honesty reporting issues so
      gathering completes successfully and independent test verification can run.'
    timestamp: '2026-06-12T18:52:05.398237'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
  - turn: 2
    decision: feedback
    feedback: '- Gathering status is ''partial_honesty_abort'' - evidence collection
      aborted before independent test verification could run. All verification fields
      (independent_tests, tests, coverage_details, bdd, arch_review, quality_gates)
      are null.: The orchestrator aborted evidence gathering due to honesty issues.
      Fix the honesty reporting issues so gathering can complete successfully and
      provide independent verification.

      - Honesty verification shows 2 critical discrepancies: Player claimed files
      ''tests/integration/test_ephemeral_fixture.py::test_data_isolation_between_projects''
      and ''tests/integration/test_ephemeral_fixture.py::test_pgvector_extension_available''
      that don''t exist on disk. These appear to be test names (with ::) incorrectly
      reported as implementation files.: Do not list test names in completion_promises.implementation_files.
      Reference only actual file paths that exist on disk.

      - Honesty verification shows 6 ''should_fix'' discrepancies: Player claimed
      files (deploy/local/docker-compose.yml, deploy/local/initdb/01_extensions.sql,
      tests/conftest.py, tests/integration/conftest.py, tests/integration/test_ephemeral_fixture.py,
      tests/unit/test_fake_embed_fixture.py) that are tracked in git but show no changes
      in ''git status --porcelain'' for this turn.: When delegating to task-work,
      do not sweep delegated outputs into files_modified, files_created, or completion_promises.implementation_files
      as if you modified them directly. Report files_modified: [] and files_created:
      [] for your own work. Use files_authored to reference delegation outputs, and
      in completion_promises.evidence, clearly attribute to the delegated agent (e.g.,
      ''task-work agent created...'').

      ... and 1 more issues'
    timestamp: '2026-06-12T19:04:06.958005'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
  - turn: 3
    decision: approve
    feedback: null
    timestamp: '2026-06-12T19:11:44.801285'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Local ephemeral compose and pytest fixtures

## Description

The hermeticity backbone: `deploy/local/docker-compose.yml` providing the
ephemeral, random-port, throwaway Postgres 16 + pgvector instance used by ALL
automated test gates (including AutoBuild), plus the pytest fixtures that
orchestrate it. Each test session mints a UUID-seeded compose project name
(`fleet_memory_test_<uid>`) and a random host port, registers `atexit` cleanup so
aborted runs leave no trace, and skips fast with a clear diagnostic when Docker is
absent. Parallel worktrees each get their own conflict-free instance.
**AutoBuild must never depend on the NAS.**

## Acceptance Criteria

- [ ] `deploy/local/docker-compose.yml` exists: image `pgvector/pgvector:pg16`, host port env-overridable (no fixed 5432 binding; fixture assigns a free random port), mounts `./initdb` to `/docker-entrypoint-initdb.d`, defines a `pg_isready` healthcheck with `interval: 2s`, `retries: 10` (review risk R4 — the fixture waits on health, not the port)
- [ ] `deploy/local/initdb/01_extensions.sql` contains `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] With Docker unavailable, an explicit `python -m pytest tests/integration/ -m integration` run fails/skips quickly (no hang) with a message naming Docker / the container runtime as the missing prerequisite
- [ ] The session-scoped `ephemeral_pg` fixture yields a plain `postgresql://` DSN at `127.0.0.1` on a non-5432 random port; after session teardown `docker compose -p <project> ps -q` is empty and the anonymous volume is removed (`down -v`) — verified by a minimal integration self-test
- [ ] After fixture startup, `SELECT extname FROM pg_extension` includes `vector` (init script ran on the fresh volume — review risk R3)
- [ ] Two fixture instantiations with distinct project uids yield DSNs on different ports with mutually invisible data (parallel-isolation self-test)
- [ ] `tests/conftest.py` exports a `fake_embed` fixture whose fake is defined INLINE (deterministic 768-dim vectors, no import from `fleet_memory.embed` — that module lands in a later wave); using it alone opens no database or network connection
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] A marker-gated self-test (`tests/integration/test_ephemeral_fixture.py`) exercising fixture startup, pgvector presence, random port, teardown emptiness
- [ ] `atexit`-registered `docker compose -p <project> down -v` covers SIGINT/aborted runs

## BDD Scenarios Covered

- "An ephemeral test instance provides a fresh database for a test run"
- "Parallel test runs each get their own isolated ephemeral instance"
- "An aborted test run still leaves no trace behind"
- "An explicitly requested integration run fails clearly when no ephemeral instance can start"
- "The full test suite passes with the durable shared instance powered off" (foundation)
- "Unit tests pass with no database and no embedding service available" (fake_embed fixture)

## Implementation Notes

- Project name: `fleet_memory_test_{uuid4().hex[:8]}` — underscores only
- Random port: bind a socket to port 0, read the assigned port, release, pass as `PGPORT` env to compose (small race window is acceptable; compose fails loudly on collision and the fixture may retry once)
- Teardown order: `request.addfinalizer` for normal exit; `atexit.register` as the abort net; both idempotent
- DSN shape: `postgresql://fleet_memory:fleet_memory@127.0.0.1:{port}/fleet_memory` — credentials are test-only constants in the compose file, never reused for the NAS
- Keep `tests/integration/conftest.py` self-contained: reads env, shells to `docker compose`; does NOT import `fleet_memory.settings`
