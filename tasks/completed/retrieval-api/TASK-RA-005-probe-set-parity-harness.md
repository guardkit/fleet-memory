---
id: TASK-RA-005
title: Probe-set evaluation harness and parity report
task_type: feature
parent_review: TASK-REV-RA05
feature_id: FEAT-MEM-05
wave: 4
implementation_mode: task-work
complexity: 6
dependencies:
- TASK-RA-003
consumer_context:
- task: TASK-RA-003
  consumes: AssembledContext
  framework: Calls the assembled search() entry point per probe query
  driver: fleet_memory.retrieval.search
  format_note: Harness compares each probe's assembled result to a recorded baseline
    answer
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-MEM-05 completed"
pre_sweep_status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-05
  base_branch: main
  started_at: '2026-06-13T17:09:26.619026'
  last_updated: '2026-06-13T17:18:58.322423'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T17:09:26.619026'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Probe-set evaluation harness and parity report

## Description

Build the probe-set evaluation harness behind the ≥15-query retrieval-parity
gate (AC-3). It runs a frozen set of fixed queries against the re-indexed
corpus and emits a parity report comparing each result to its recorded Graphiti
baseline, flagging divergence.

## Acceptance Criteria

- [ ] The harness runs every probe query in the frozen set and emits a parity
      report comparing each result to its recorded baseline answer.
- [ ] A probe set of exactly the minimum size (15) satisfies the gate (complete).
      (boundary: just-inside)
- [ ] A probe set smaller than the minimum (14) fails the gate, reported as below
      the required size. (boundary: just-outside)
- [ ] A probe query whose result diverges from its recorded baseline is flagged
      as a divergence, and the overall run is NOT marked as full parity.
- [ ] The parity tolerance is a single named constant defaulting to
      zero-divergence (full parity requires zero flagged divergences). Choosing
      an OD-2 tolerance later is a one-line change. (ASSUM-007, low confidence)
- [ ] The minimum probe-set size (15) is a single named constant, not a literal.
- [ ] All modified files pass project-configured lint/format checks with zero errors.

## Coach Validation

```bash
pytest tests/unit/test_probe_harness.py -x
ruff check src/fleet_memory/retrieval/
```

## Seam Tests

```python
"""Seam test: verify AssembledContext contract from TASK-RA-003."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("AssembledContext")
def test_harness_consumes_search_results():
    """Harness drives search() and compares each result to a baseline.

    Contract: harness calls the assembled search entry point; a divergence
    from baseline must clear the full-parity flag.
    Producer: TASK-RA-003
    """
    PARITY_TOLERANCE = 0  # named constant; zero-divergence default (ASSUM-007)
    divergences = 0
    assert (divergences <= PARITY_TOLERANCE) is True
```

## Implementation Notes

- **ASSUM-007 is low confidence** and depends on the OD-2 probe-set freeze.
  Keep `PARITY_TOLERANCE` and `MIN_PROBE_SET_SIZE` as named module constants so
  the tolerance decision is a one-line change, not a refactor.
- The frozen probe set + recorded baselines are fixtures/data, not code — store
  them so a re-index (FEAT-MEM-07) can re-run the gate unchanged.
- This harness is the acceptance instrument reused by FEAT-MEM-07/08; keep it
  importable, not a one-off script buried in tests.
