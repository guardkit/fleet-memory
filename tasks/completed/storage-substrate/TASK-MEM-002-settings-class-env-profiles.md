---
id: TASK-MEM-002
title: Settings class and env profiles
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-CA81 completed"
pre_sweep_status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: declarative
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 2
implementation_mode: direct
complexity: 3
estimated_minutes: 35
dependencies:
- TASK-MEM-001
tags:
- pydantic-settings
- configuration
- assumptions
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T18:52:05.397808'
  last_updated: '2026-06-12T18:56:41.536331'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T18:52:05.397808'
    player_summary: Implemented a complete Settings class using pydantic-settings
      with FLEET_MEMORY_ environment variable prefix. The class includes two required
      fields (pg_dsn and embed_url) with empty-string validation, and seven optional
      fields with carefully documented defaults. Created comprehensive .env.example
      with clearly separated mac-dev and test configuration blocks. All timeout and
      pool size defaults are marked as ASSUM-004/006/008 placeholders pending verification
      in TASK-MEM-013. The implementation is
    player_success: true
    coach_success: true
---

# Task: Settings class and env profiles

## Description

Single pydantic-settings `Settings` class with `env_prefix = "FLEET_MEMORY_"` and
`.env` file support, plus a committed `.env.example` documenting the `mac-dev`
(durable NAS target over LAN/Tailscale) and `test` (ephemeral target) profiles.
The three low-confidence assumption placeholders become documented field defaults:
ASSUM-004 → `pg_pool_max=10`, ASSUM-006 → `pg_connect_timeout_s=10.0`,
ASSUM-008 → `embed_timeout_s=10.0`. A production/GB10 profile is deferred to
FEAT-MEM-04 (OD-5) — note this in `.env.example` comments.

## Acceptance Criteria

- [ ] `src/fleet_memory/settings.py` exports `Settings` with fields: `pg_dsn` (required), `embed_url` (required), `embed_model: str = "nomic-embed-text-v1.5"`, `embed_dims: int = 768`, `embed_timeout_s: float = 10.0`, `pg_pool_min: int = 2`, `pg_pool_max: int = 10`, `pg_connect_timeout_s: float = 10.0`, `nats_url: str = "nats://localhost:4222"`; verified by `python -c "from fleet_memory.settings import Settings; s = Settings(FLEET_MEMORY_PG_DSN='postgresql://u:p@localhost/db', FLEET_MEMORY_EMBED_URL='http://localhost:9000'); assert s.pg_pool_max == 10 and s.embed_timeout_s == 10.0 and s.pg_connect_timeout_s == 10.0"` exiting 0
- [ ] `python -c "from fleet_memory.settings import Settings; Settings()"` with no `FLEET_MEMORY_` env raises `ValidationError` whose message names each missing field
- [ ] `.env.example` exists with clearly labelled `mac-dev` and `test` blocks, documents every `FLEET_MEMORY_` field, uses plain `postgresql://` DSN format (psycopg3 conninfo — no `+asyncpg` suffix), and carries inline comments marking `pg_pool_max` / `pg_connect_timeout_s` / `embed_timeout_s` as ASSUM-004/006/008 placeholders pending verification (TASK-MEM-013)
- [ ] `python -m pytest tests/unit/test_settings.py -v` passes covering: missing-field error names each field, all defaults match the documented placeholders, `FLEET_MEMORY_` prefix isolation (unprefixed `PG_DSN` env is ignored), and OS env vars take precedence over `.env` file values (review risk R6)
- [ ] Empty-string `FLEET_MEMORY_PG_DSN` or `FLEET_MEMORY_EMBED_URL` raises `ValidationError`
- [ ] `settings.py` imports no NATS, no httpx, no psycopg — pure pydantic-settings
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_settings.py` — hermetic (no network, no database)

## BDD Scenarios Covered

- "Configuration profiles select the correct deployment target from the environment"
- "Missing required settings prevent startup with a clear message"

## Implementation Notes

- `model_config = SettingsConfigDict(env_prefix="FLEET_MEMORY_", env_file=".env", env_file_encoding="utf-8")`
- pydantic-settings v2 gives env vars precedence over `.env` by default — assert it explicitly so a stray operator `.env` pointing at the NAS can never hijack the test tier
- Keep DSN type permissive enough for both `postgresql://` and unix-socket forms; validate non-empty
