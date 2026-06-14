---
complexity: 4
created: 2026-06-13 20:30:00+00:00
dependencies:
- TASK-RIP-005
- TASK-RIP-006
estimated_minutes: 60
feature_id: FEAT-MEM-07
id: TASK-RIP-009
implementation_mode: task-work
parent_review: TASK-REV-RIP7
priority: high
status: design_approved
tags:
- reindex
- cli
- resilience
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: Re-index CLI entrypoint (fail-loud, resumable)
updated: 2026-06-13 20:30:00+00:00
wave: 6
---

# Task: Re-index CLI entrypoint (fail-loud, resumable)

## Description

`python -m fleet_memory.reindex` — the operator entry point. Wires settings
(corpus root, backfill dir), runs the orchestrator (TASK-RIP-005) and the backfill
gate (TASK-RIP-006), prints the `RunReport`, and **surfaces failures loudly**:
a relay/store outage mid-run reports failure with the affected documents named and
exits non-zero — never a silent partial run. Re-running after an interruption
publishes every document that did not reach the store; downstream idempotent
upsert guarantees no duplicates from the documents published before the
interruption.

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/__main__.py` runs a full re-index (deterministic corpus + reviewed backfill) from settings and prints the `RunReport`
- [ ] A relay/store outage mid-run causes the run to report failure with the affected documents **named** (no silent skip), and the process exits non-zero
- [ ] Re-running after a partial/interrupted run publishes every document that did not reach the store and produces no duplicate record (downstream upsert)
- [ ] `python -m fleet_memory.reindex --help` exits 0 and does not require a live connection
- [ ] `tests/unit/reindex/test_cli.py` covers failure-surfacing with a fake publisher that raises partway through
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_cli.py::test_midrun_failure_names_affected_documents_and_exits_nonzero`
- [ ] `test_cli.py::test_help_exits_zero_without_connection`

## BDD Scenarios Covered

- "A relay or store outage mid-run fails loudly and loses no document"
- "A run interrupted partway through can be safely re-run to completion"

## Implementation Notes

- Resumability is *not* new state in the CLI — it falls out of the writer's
  natural-key upsert. The CLI's only resilience job is to fail loudly and name
  what didn't land, so a re-run is a safe no-op for what already stored.
- Build the store/broker via the existing [app.py](src/fleet_memory/app.py) wiring;
  honour `pg_connect_timeout_s` so an unreachable store fails fast rather than hanging.