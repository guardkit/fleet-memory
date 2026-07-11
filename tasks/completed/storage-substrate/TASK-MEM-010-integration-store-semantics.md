---
id: TASK-MEM-010
title: 'Integration tests: store semantics and pool lifecycle'
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-CA81 completed"
pre_sweep_status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 6
implementation_mode: task-work
complexity: 6
estimated_minutes: 90
dependencies:
- TASK-MEM-004
- TASK-MEM-005
- TASK-MEM-006
tags:
- integration-tests
- marker-gated
- pool
- semantics
consumer_context:
- task: TASK-MEM-004
  consumes: EPHEMERAL_PG_DSN
  framework: pytest session fixture (ephemeral_pg)
  driver: docker compose + psycopg3
  format_note: Plain postgresql:// DSN at 127.0.0.1 on a random non-5432 port; throwaway
    data; NEVER the NAS host
- task: TASK-MEM-005
  consumes: STORE_CONTEXT
  framework: langgraph AsyncPostgresStore
  driver: psycopg3 + psycopg-pool
  format_note: async_store_context(settings, embed_fn) yields a ready store; setup()
    idempotent
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T21:57:19.788261'
  last_updated: '2026-06-12T22:08:59.315550'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T21:57:19.788261'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Integration tests — store semantics and pool lifecycle

## Description

Marker-gated (`@pytest.mark.integration`) tests against the ephemeral Postgres
instance with REAL nomic embeddings from GB10 llama-swap (:9000) over Tailscale.
Covers the core store semantics (round-trip, upsert, delete, ranked semantic
search) and the pool lifecycle, including the ASSUM-004 and ASSUM-006
verifications with record-and-revise semantics. The NAS is never referenced.

## Acceptance Criteria

- [ ] `python -m pytest tests/integration/ -m integration -v --timeout=120` passes against the ephemeral instance; no test references any NAS DSN
- [ ] Round-trip: `aput` then `aget` returns byte-identical content with `created_at`/`updated_at` present
- [ ] Upsert: two `aput` calls to the same key leave exactly one record; `aget` returns the second version only; delete: after `adelete`, both `aget` and `asearch` return nothing for the key
- [ ] Ranking: with memories about "database connection pooling" and "holiday rota planning" stored, `asearch("how do we manage Postgres connections")` ranks the pooling memory first and every result carries a relevance score (real nomic round-trip proven)
- [ ] Pool lifecycle: enter → `aput` → exit leaks no connection (`pg_stat_activity` count restored); `store.setup()` run twice is idempotent; ASSUM-006: actual observed connect-timeout against a closed port recorded in a test comment
- [ ] Pool pressure (ASSUM-004): 15 concurrent `aput` calls against `pg_pool_max=10` — record the actual psycopg-pool behaviour: if operations queue and all 15 complete within a 30 s bound the assumption holds; if the pool raises a timeout error instead, capture it, adjust the test to assert the actual contract, and flag the revised value for TASK-MEM-013

## Test Requirements

- [ ] Files: `tests/integration/test_store_round_trip.py`, `test_store_semantics.py`, `test_pool_lifecycle.py`
- [ ] Requires: Docker running, Tailscale route to GB10 — documented in module docstrings; the default (non-integration) run never executes these

## BDD Scenarios Covered

- "Storing a memory and retrieving it by its key"
- "Storing to an existing key replaces the previous memory"
- "Deleting a memory removes it from retrieval and search"
- "Semantic search returns memories ranked by relevance to the query"
- "The connection pool lives and dies with the service"
- "Operations beyond pool capacity queue rather than fail"
- "The full test suite passes with the durable shared instance powered off"

## Implementation Notes

- Build `Settings` for the test from the `ephemeral_pg` fixture DSN + the real GB10 embed URL (env-provided, e.g. `FLEET_MEMORY_EMBED_URL` in the developer's shell or a test-tier `.env` block)
- Namespace per test: `("fleet_memory", "test_<uuid>", "memory")` — isolation inside the shared session instance
- pg_stat_activity comparison must filter to the test database name to avoid flakiness

## Seam Tests

```python
"""Seam test: verify EPHEMERAL_PG_DSN contract from TASK-MEM-004."""
import pytest


@pytest.mark.seam
@pytest.mark.integration
@pytest.mark.integration_contract("EPHEMERAL_PG_DSN")
def test_ephemeral_dsn_is_local_random_port(ephemeral_pg):
    """Verify the fixture DSN targets localhost on a random, non-NAS port.

    Contract: plain postgresql:// at 127.0.0.1, port != 5432, never the NAS.
    Producer: TASK-MEM-004
    """
    dsn = ephemeral_pg
    assert dsn.startswith("postgresql://"), f"Expected plain postgresql:// conninfo, got: {dsn}"
    assert "127.0.0.1" in dsn or "localhost" in dsn, f"Ephemeral instance must be local: {dsn}"
    assert ":5432/" not in dsn, "Ephemeral instance must not squat the default Postgres port"
    for forbidden in ("synology", "nas", "100.64."):
        assert forbidden not in dsn.lower(), f"NAS reference leaked into ephemeral DSN: {dsn}"
```
