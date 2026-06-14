---
complexity: 5
created: 2026-06-13 20:30:00+00:00
dependencies:
- TASK-RIP-005
estimated_minutes: 75
feature_id: FEAT-MEM-07
id: TASK-RIP-008
implementation_mode: task-work
parent_review: TASK-REV-RIP7
priority: high
status: design_approved
tags:
- reindex
- parity
- probe-set
- retrieval
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: Probe-set parity report generator
updated: 2026-06-13 20:30:00+00:00
wave: 5
---

# Task: Probe-set parity report generator

## Description

Generate a probe-set parity report against the re-indexed corpus (FEAT-MEM-07
AC-4, which feeds AC-1's retrieval-quality criterion). Reuse the **existing**
`src/fleet_memory/retrieval/probe_harness.py` from FEAT-MEM-05 to run the frozen probe set against
the re-indexed store and report per-probe hit/miss plus an aggregate parity
figure. This task builds the report generator; running it against the live
re-indexed corpus is part of the operator verification (TASK-RIP-011).

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/parity.py` runs the frozen probe set via the existing `src/fleet_memory/retrieval/probe_harness.py` against the re-indexed store and emits a parity report
- [ ] The report records per-probe hit/miss and an aggregate parity figure
- [ ] Retrieval logic is **reused** from [src/fleet_memory/retrieval/probe_harness.py](src/fleet_memory/retrieval/probe_harness.py) — no duplicate retrieval implementation
- [ ] `tests/unit/reindex/test_parity.py` runs against an ephemeral/fake store seeded with known records and known probes and asserts the report shape and parity calculation
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_parity.py::test_parity_report_shape`
- [ ] `test_parity.py::test_aggregate_parity_calculation`

## BDD Scenarios Covered

- (No dedicated `.feature` scenario — AC-4 is reporting tooling that feeds AC-1.)

## Implementation Notes

- Do not re-implement search or ranking — import and drive the probe harness.
- The frozen probe set composition is owned by FEAT-MEM-05 (OD-2); read it from
  wherever the harness already expects it rather than redefining it here.
- Keep the report machine-readable (JSON) so the operator run (TASK-RIP-011) can
  attach it to the verification record.