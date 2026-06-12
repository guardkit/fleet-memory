---
complexity: 4
consumer_context:
- consumes: STORE_CONTEXT
  driver: langgraph AsyncPostgresStore via async_store_context
  format_note: asynccontextmanager yielding a ready AsyncPostgresStore (setup() already
    run); entering connects + verifies, exiting releases every connection
  framework: FastStream lifespan context manager
  task: TASK-MEM-005
created: 2026-06-12 17:00:00+00:00
dependencies:
- TASK-MEM-003
- TASK-MEM-005
estimated_minutes: 45
feature_id: FEAT-CA81
id: TASK-MEM-006
implementation_mode: task-work
parent_review: TASK-REV-CA81
priority: high
status: design_approved
tags:
- faststream
- lifespan
- app-shell
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: App shell with lifespan-managed store
updated: 2026-06-12 17:00:00+00:00
wave: 5
---

# Task: App shell with lifespan-managed store

## Description

Minimal FastStream app shell per the nats-asyncio-service template idiom:
module-level `broker = NatsBroker(settings.nats_url)`, `FastStream(broker)` app
with a lifespan that enters `async_store_context` and exposes the store to future
handlers. NO subscribers yet — FEAT-MEM-04 slots its MEMORY-stream consumer into
this shell without restructuring. Startup against an unreachable database fails
fast with a diagnostic naming the target (ASSUM-006), and the layer boundary holds:
store/embed/settings modules contain zero NATS imports.

## Acceptance Criteria

- [ ] `src/fleet_memory/app.py` exports module-level `broker` and a `FastStream` app whose lifespan enters `async_store_context(settings)` and exposes the store (app/broker context attribute); no `@broker.subscriber` present; `python -c "from fleet_memory.app import app, broker"` exits 0 with required `FLEET_MEMORY_` env set
- [ ] Lifespan unit test using `TestNatsBroker` enters and exits cleanly with a fake embed and a mocked/stubbed store context — no real NATS, no real Postgres
- [ ] Startup-failure unit test: with a DSN pointing at a closed local port and the REAL store context, lifespan entry raises within `pg_connect_timeout_s` plus slack (test wall-clock under 15 s) and the error names the database target without leaking the password — ASSUM-006 verification: record the actual observed driver timeout behaviour in a test comment
- [ ] `grep -rE "from nats|import nats|faststream" src/fleet_memory/store.py src/fleet_memory/embed.py src/fleet_memory/settings.py` exits non-zero (service layers carry zero broker imports — handler/service boundary)
- [ ] `python -m pytest tests/unit/test_app_lifespan.py -v` passes
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_app_lifespan.py` — TestNatsBroker pattern; no network beyond the deliberately-refused localhost port in the failure test

## BDD Scenarios Covered

- "The connection pool lives and dies with the service"
- "The service refuses to start when the database is unreachable"
- "Missing required settings prevent startup with a clear message" (entry point surfaces Settings ValidationError)

## Implementation Notes

- Settings construction happens inside app assembly (factory function) so import-time side effects stay minimal and tests can inject env
- `nats_url` has a benign default; no NATS connection is attempted during unit tests (TestNatsBroker patches it)
- Fail-fast diagnostic format: name host + database, never the password (credential-hygiene scenario)

## Seam Tests

```python
"""Seam test: verify STORE_CONTEXT contract from TASK-MEM-005."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("STORE_CONTEXT")
async def test_store_context_yields_ready_store(monkeypatch):
    """Verify async_store_context is an asynccontextmanager yielding a store.

    Contract: entering runs setup() and yields a ready AsyncPostgresStore;
    exiting releases connections. Unit tier verifies the SHAPE with a stub.
    Producer: TASK-MEM-005
    """
    import contextlib
    from fleet_memory import store as store_mod
    assert hasattr(store_mod, "async_store_context")
    cm = store_mod.async_store_context  # must be usable as: async with cm(settings, embed_fn) as s:
    assert callable(cm)
    # Shape check only in unit tier — wave-6 integration tests enter it for real.
```