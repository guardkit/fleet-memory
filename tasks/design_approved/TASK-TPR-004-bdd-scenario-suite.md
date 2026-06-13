---
complexity: 4
dependencies:
- TASK-TPR-003
feature_id: FEAT-MEM-02
id: TASK-TPR-004
implementation_mode: task-work
parent_review: TASK-REV-C42F
status: design_approved
tags:
- testing
- bdd
- pytest-bdd
- fleet-memory
task_type: testing
title: BDD scenario suite for typed payload registry
wave: 4
---

# Task: BDD scenario suite for typed payload registry

## Description

Wire the 29 authored Gherkin scenarios as the executable acceptance suite
using `pytest-bdd` (already a dev dependency, `pytest-bdd>=8.1,<9`). This is
the BDD-driven testing approach chosen at planning time: the
`.feature` file is the source of truth, step definitions bind it to the
`fleet_memory.payloads` implementation.

**Feature file:**
`features/typed-payload-registry/typed-payload-registry.feature`
**Step definitions:** `tests/bdd/test_typed_payload_registry.py`
(create `tests/bdd/__init__.py`).

## Acceptance Criteria

- [ ] All 29 scenarios in the feature file have step definitions and pass.
- [ ] Both `Scenario Outline` blocks (every-type-dispatchable, supersession
      count, wrong-segment-count) are parametrised and pass for every example
      row.
- [ ] Scenarios tagged `@regression` (determinism, byte-identical,
      bijection) pass.
- [ ] Negative scenarios assert on the error condition AND the error message
      content (e.g. "underscores", "not a valid natural key", names the
      missing/unknown field).
- [ ] The suite runs under the default pytest selection (it is not marked
      `integration` — no broker or infrastructure required).

## Coach Validation

```bash
pytest tests/bdd/ -v
pytest tests/ -v
```

## Notes

- No live infrastructure: every scenario acts on a payload or the registry
  in-process. Pure unit-level BDD.
- Step definitions should import from the public surface
  (`fleet_memory.payloads`), not reach into private modules, so the suite
  doubles as a contract test for the package's exports.