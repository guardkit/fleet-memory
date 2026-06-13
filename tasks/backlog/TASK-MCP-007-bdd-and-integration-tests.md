---
id: TASK-MCP-007
title: Wire the BDD scenario suite and end-to-end integration tests
status: backlog
created: 2026-06-13T16:30:00Z
updated: 2026-06-13T16:30:00Z
priority: high
task_type: testing
parent_review: TASK-REV-MEM06
feature_id: FEAT-MEM-06
wave: 4
implementation_mode: task-work
complexity: 5
estimated_minutes: 90
dependencies: [TASK-MCP-003, TASK-MCP-004, TASK-MCP-005, TASK-MCP-006]
tags: [mcp, bdd, pytest-bdd, integration, tests]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Wire the BDD scenario suite and end-to-end integration tests

## Description

Bind the 31 scenarios in
[memory-mcp-server.feature](features/memory-mcp-server/memory-mcp-server.feature)
to the implemented MCP surface using `pytest-bdd`, following the existing pattern
in [tests/bdd/test_typed_payload_registry.py](tests/bdd/test_typed_payload_registry.py).
This is the executable acceptance suite for FEAT-MEM-06. It also resolves the
single shared touch-point from the parallel Wave 3 — the `register_all`
wiring in `server.py` — so every tool and the resource are advertised by one
fully-assembled server.

Where a scenario requires the FEAT-MEM-05 retrieval module (not yet merged to
`src/`), gate it with `pytest.importorskip("fleet_memory.retrieval")` so the
suite is green today and lights up automatically once the module lands.

## Acceptance Criteria

- [ ] `tests/bdd/test_memory_mcp_server.py` exists and uses `scenarios("...memory-mcp-server.feature")` to bind the feature file
- [ ] All non-degradation, non-retrieval scenarios pass against the in-process server with a fake/in-memory store
- [ ] Degradation scenarios assert the structured tool-error result AND that the server remains running (no crash) — store-down, embedding-down, startup-while-store-down
- [ ] Retrieval-dependent scenarios are gated with `pytest.importorskip("fleet_memory.retrieval")` and pass once FEAT-MEM-05 is merged
- [ ] Integration-marked end-to-end test: launch the server as a stdio subprocess, list tools (assert search/write/supersede advertised), write a typed ADR and find it by search (the headline write-then-find scenario)
- [ ] `pytest tests/ -q` (default, integration excluded) is green; `pytest -m integration` runs the stdio/parity tests when infrastructure is available
- [ ] The `register_all` wiring in `server.py` advertises all three tools and the `memory://projects` resource

## Test Requirements

- [ ] `tests/bdd/test_memory_mcp_server.py` collects and passes the non-gated scenarios under the default marker set
- [ ] `tests/integration/test_mcp_stdio_e2e.py::test_write_then_find` (`@pytest.mark.integration`)
- [ ] `tests/integration/test_mcp_stdio_e2e.py::test_tools_advertised_over_stdio` (`@pytest.mark.integration`)
- [ ] No new default-collected test requires a live Postgres or embedding service

## BDD Scenarios Covered

- (Harness) Binds all 31 scenarios in memory-mcp-server.feature; owns the
  cross-tool e2e scenarios: "An MCP client writes a typed ADR and then finds it
  by search" (full path) and the stdio transport / tool-advertisement scenarios.

## Implementation Notes

- Follow [tests/bdd/test_typed_payload_registry.py](tests/bdd/test_typed_payload_registry.py)
  for step-definition style (`given`/`when`/`then`, `parsers`, in-process fixtures).
- Reuse the fake embedding fixture
  ([tests/unit/test_fake_embed_fixture.py](tests/unit/test_fake_embed_fixture.py))
  and any in-memory store helper already used by the writer tests.
- For the stdio e2e test, spawn `python -m fleet_memory.mcp` and drive it with an
  MCP client over stdio; keep it `@pytest.mark.integration` so the default run
  stays infrastructure-free.
- This task is the integration point for the Wave-3 `register_all` merge — confirm
  the four registrations are present and de-duplicated.
