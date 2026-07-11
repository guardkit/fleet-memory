---
id: TASK-RA-004
title: Job-specific composition by complexity band
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
  framework: In-process assembled-block + coverage result from the assembly task
  driver: fleet_memory.retrieval assembly return type
  format_note: Composition adjusts type mix and per-type budget share before assembly
    renders the block
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-MEM-05 completed"
pre_sweep_status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-05
  base_branch: main
  started_at: '2026-06-13T17:09:26.618697'
  last_updated: '2026-06-13T17:25:02.628693'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T17:09:26.618697'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Job-specific composition by complexity band

## Description

Port guardkit's job-specific context composition: the type mix and per-type
budget share shift with the job's complexity band (`simple` / `standard` /
`complex`), composing overview/patterns/warnings differently while staying
within budget.

## Acceptance Criteria

- [ ] `search`/assembly accepts a complexity band of `simple`, `standard`, or
      `complex` that controls the type mix and per-type budget share.
- [ ] Given identical matching memories, the `complex` job's block includes more
      patterns and warnings than the `simple` job's block.
- [ ] Both the `simple` and `complex` blocks remain within their token budgets
      (composition never overrides the AC-1 budget guarantee).
- [ ] The three band names are defined as a single source of truth (enum/constant),
      not scattered string literals. (ASSUM-001, low confidence — verify against
      guardkit's actual job-specific builder before FEAT-MEM-08 cutover)
- [ ] All modified files pass project-configured lint/format checks with zero errors.

## Coach Validation

```bash
pytest tests/unit/test_composition.py -x
ruff check src/fleet_memory/retrieval/
```

## Seam Tests

```python
"""Seam test: verify AssembledContext contract from TASK-RA-003."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("AssembledContext")
def test_composition_respects_budget_from_assembly():
    """Composition tunes the mix but assembly still enforces the budget.

    Contract: composition adjusts type/budget share; the assembled block must
    still not exceed token_budget.
    Producer: TASK-RA-003
    """
    # Consumer side: complex band over the same memories yields >= patterns/warnings
    # than simple band, and both blocks stay within budget.
    assert True  # replace with band-comparison + budget assertions
```

## Implementation Notes

- **ASSUM-001 is low confidence.** Read guardkit's real job-specific context
  builder before finalising the band-to-mix mapping; record the verified mapping
  in `features/retrieval-api/retrieval-api_assumptions.yaml`.
- Composition shapes the *input* to assembly (which types, what share); it must
  not bypass the tiktoken budget enforcement in TASK-RA-003.
