---
id: TASK-MEM-001
title: Scaffold project layout
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-CA81 completed"
pre_sweep_status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: scaffolding
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 1
implementation_mode: direct
complexity: 3
estimated_minutes: 40
dependencies: []
tags:
- scaffolding
- pyproject
- pytest
- ruff
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T18:11:20.768370'
  last_updated: '2026-06-12T18:15:19.848574'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T18:11:20.768370'
    player_summary: 'Created the complete project scaffold for fleet_memory including:
      (1) pyproject.toml with all required dependencies (faststream[nats], pydantic>=2,
      pydantic-settings>=2, langgraph-checkpoint-postgres>=2.0, httpx, psycopg[binary],
      psycopg-pool) and dev dependencies (pytest, pytest-asyncio, pytest-timeout,
      ruff, pyyaml); (2) src/fleet_memory package with __init__.py; (3) tests directory
      structure with unit tests; (4) pytest configuration with integration marker
      excluded by default; (5) ruff config'
    player_success: true
    coach_success: true
---

# Task: Scaffold project layout

## Description

Establish the Python project skeleton for fleet_memory. The repo currently has NO
Python scaffolding — only GuardKit structure, docs, and the BDD spec. Create
`pyproject.toml` with pinned core dependencies, the `src/fleet_memory/` package,
the `tests/unit/` + `tests/integration/` split, pytest configuration with the
`integration` marker excluded by default, and ruff configuration. All identifiers
use underscores (no hyphens anywhere — FalkorDB scar tissue).

Note: `AsyncPostgresStore` is provided by `langgraph-checkpoint-postgres`, which
uses psycopg3 + psycopg-pool (NOT asyncpg). DSNs are plain `postgresql://`
conninfo strings.

## Acceptance Criteria

- [ ] `pyproject.toml` exists with `[project]` `name = "fleet_memory"`, requires-python `>=3.12`, and pinned deps: `faststream[nats]`, `pydantic>=2`, `pydantic-settings>=2`, `langgraph-checkpoint-postgres>=2.0`, `httpx`, `psycopg[binary]`, `psycopg-pool`; dev extras: `pytest`, `pytest-asyncio`, `pytest-timeout`, `ruff`, `pyyaml`
- [ ] `pip install -e ".[dev]"` succeeds and `python -c "import fleet_memory"` exits 0
- [ ] `python -c "from langgraph.store.postgres.aio import AsyncPostgresStore"` exits 0 (confirms the pinned package exposes the store API — review risk R5)
- [ ] `tests/unit/test_scaffold.py` contains `test_package_imports` (imports `fleet_memory`); `python -m pytest tests/ -q` exits 0 with 1 passed — the `integration` marker is excluded by default via `addopts = -m "not integration"` and registered in pytest config
- [ ] `ruff check src/ tests/` exits 0
- [ ] No filename or Python identifier under `src/` or `tests/` contains a hyphen

## Test Requirements

- [ ] `tests/unit/test_scaffold.py::test_package_imports` passes
- [ ] Default pytest run collects zero `integration`-marked tests

## BDD Scenarios Covered

- "Unit tests pass with no database and no embedding service available" (structural prerequisite — marker exclusion)
- "An explicitly requested integration run fails clearly when no ephemeral instance can start" (marker gating established here)

## Implementation Notes

- Layout: `src/fleet_memory/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `pytest.ini` (or `[tool.pytest.ini_options]` in pyproject), `ruff.toml` (or `[tool.ruff]`)
- pytest config must set `asyncio_mode = "auto"` (pytest-asyncio) and register the `integration` marker so `--strict-markers` is viable later
- `.gitignore` already covers `.env*` — extend only if venv/cache patterns are missing
- The placeholder unit test gives every later wave's smoke gate a non-empty, passing `tests/unit` collection from Wave 1 onward
