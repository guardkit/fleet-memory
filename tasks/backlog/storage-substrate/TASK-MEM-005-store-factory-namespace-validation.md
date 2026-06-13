---
id: TASK-MEM-005
title: Store factory and namespace validation
status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 4
implementation_mode: task-work
complexity: 5
estimated_minutes: 55
dependencies:
- TASK-MEM-002
- TASK-MEM-003
tags:
- langgraph
- asyncpostgresstore
- pgvector
- namespaces
consumer_context:
- task: TASK-MEM-002
  consumes: FLEET_MEMORY_PG_DSN
  framework: langgraph AsyncPostgresStore (langgraph-checkpoint-postgres)
  driver: psycopg3 + psycopg-pool
  format_note: "Plain postgresql://user:pass@host:port/dbname conninfo \u2014 psycopg3\
    \ format, NO +asyncpg dialect suffix; pool sizing from pg_pool_min/pg_pool_max,\
    \ connect bound from pg_connect_timeout_s"
- task: TASK-MEM-003
  consumes: EMBED_CALLABLE
  framework: AsyncPostgresStore index config
  driver: httpx (inside the callable)
  format_note: async callable list[str] -> list[list[float]], exactly settings.embed_dims
    (768) floats per vector; raises EmbedDimensionError/EmbedTimeoutError/EmbedServiceError
    on failure
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T19:34:00.722792'
  last_updated: '2026-06-12T19:44:53.271926'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T19:34:00.722792'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Store factory and namespace validation

## Description

`src/fleet_memory/store.py`: an `asynccontextmanager` `async_store_context(settings,
embed_fn=None)` that yields a configured `AsyncPostgresStore` with index config
`{"dims": settings.embed_dims, "embed": <callable>, "fields": ["content"]}`, plus
`validate_namespace()` enforcing underscores-only identifiers at validation time —
before anything reaches the database. When `embed_fn` is None the real httpx
callable is constructed from settings; tests inject fakes.

## Acceptance Criteria

- [ ] `src/fleet_memory/store.py` exports `async_store_context(settings, embed_fn=None)` as an asynccontextmanager yielding `AsyncPostgresStore`; entering it runs `store.setup()`; exiting closes the pool cleanly
- [ ] `validate_namespace(("fleet_memory", "my-project", "chunk"))` raises `NamespaceValidationError` whose message states identifiers must use underscores; `validate_namespace(("fleet_memory", "fleet_memory", "adr"))` passes — enforcement happens before any database call
- [ ] `python -m pytest tests/unit/test_store_validation.py -v` passes with no database and no network (the factory is constructed but never entered in the unit tier)
- [ ] `grep -rE "import psycopg|from psycopg|import asyncpg" tests/unit/` exits non-zero (no direct driver imports in unit tests — hermeticity of the unit tier)
- [ ] Driver/API verification recorded (review risk R5): confirm against the installed `langgraph-checkpoint-postgres` version that (a) the conninfo is plain `postgresql://` psycopg3 format, (b) the index-config key shape `{dims, embed, fields}` matches the constructor signature, (c) pool min/max from settings flow into the actual pool — record findings as comments in `store.py`
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_store_validation.py` — namespace acceptance/rejection table, factory construction with `make_fake_embed`, no `__aenter__` in unit tier

## BDD Scenarios Covered

- "A namespace containing hyphens is rejected"
- "Storing a memory and retrieving it by its key" (factory prerequisite)
- "The connection pool lives and dies with the service" (context-manager shape)

## Implementation Notes

- `from langgraph.store.postgres.aio import AsyncPostgresStore`; prefer `AsyncPostgresStore.from_conn_string(...)` or explicit pool construction — whichever the pinned version documents for pool-size + timeout control
- Pass `settings.pg_connect_timeout_s` into pool/connection acquisition so ASSUM-006 has a real lever
- Namespace rule: every tuple element matches `^[a-z0-9_]+$`
- Credential hygiene: any exception raised out of the context manager must not interpolate the DSN password (strip/passwordless repr)

## Seam Tests

The following seam test validates the integration contracts with TASK-MEM-002 (DSN format) and TASK-MEM-003 (embed callable). Implement it to verify the boundary before integration.

```python
"""Seam test: verify FLEET_MEMORY_PG_DSN and EMBED_CALLABLE contracts."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("FLEET_MEMORY_PG_DSN")
def test_pg_dsn_format_is_psycopg3_conninfo():
    """Verify the DSN is plain postgresql:// psycopg3 conninfo.

    Contract: plain postgresql:// — NO +asyncpg dialect suffix (psycopg3 driver).
    Producer: TASK-MEM-002
    """
    from fleet_memory.settings import Settings
    s = Settings(FLEET_MEMORY_PG_DSN="postgresql://u:p@localhost:5499/db",
                 FLEET_MEMORY_EMBED_URL="http://localhost:9000")
    dsn = str(s.pg_dsn)
    assert dsn.startswith("postgresql://"), f"Expected plain postgresql:// conninfo, got: {dsn}"
    assert "+asyncpg" not in dsn, f"psycopg3 conninfo must not carry +asyncpg suffix: {dsn}"


@pytest.mark.seam
@pytest.mark.integration_contract("EMBED_CALLABLE")
async def test_embed_callable_returns_768_dim_vectors():
    """Verify the embed callable contract consumed by the store index config.

    Contract: async list[str] -> list[list[float]], exactly 768 floats per vector.
    Producer: TASK-MEM-003
    """
    from fleet_memory.embed import make_fake_embed
    embed = make_fake_embed(768)
    vectors = await embed(["one text", "two text"])
    assert len(vectors) == 2
    assert all(len(v) == 768 for v in vectors), "Every vector must be exactly 768 dims"
```
