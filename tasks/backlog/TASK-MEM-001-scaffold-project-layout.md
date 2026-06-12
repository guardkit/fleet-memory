---
id: TASK-MEM-001
title: Scaffold project layout
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: scaffolding
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 1
implementation_mode: direct
complexity: 3
estimated_minutes: 40
dependencies: []
tags: [scaffolding, pyproject, pytest, ruff]
test_results:
  status: pending
  coverage: null
  last_run: null
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
