---
complexity: 5
created: 2026-06-12 17:00:00+00:00
dependencies:
- TASK-MEM-001
estimated_minutes: 60
feature_id: FEAT-CA81
id: TASK-MEM-004
implementation_mode: task-work
parent_review: TASK-REV-CA81
priority: high
status: design_approved
tags:
- docker-compose
- pgvector
- hermetic-testing
- fixtures
task_type: infrastructure
test_results:
  coverage: null
  last_run: null
  status: pending
title: Local ephemeral compose and pytest fixtures
updated: 2026-06-12 17:00:00+00:00
wave: 2
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