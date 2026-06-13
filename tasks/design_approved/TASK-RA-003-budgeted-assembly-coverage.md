---
complexity: 6
consumer_context:
- consumes: RankedResults
  driver: fleet_memory.retrieval search-core return type
  format_note: Ordered most-relevant-first; assembly drops from the tail to fit the
    budget
  framework: In-process list of ranked, supersession-resolved memories with scores
  task: TASK-RA-002
dependencies:
- TASK-RA-002
feature_id: FEAT-MEM-05
id: TASK-RA-003
implementation_mode: task-work
parent_review: TASK-REV-RA05
status: design_approved
task_type: feature
title: Token-budgeted context assembly and coverage score
wave: 3
---

# Task: Token-budgeted context assembly and coverage score

## Description

Assemble the ranked memories from search core into a single context block that
never exceeds the token budget, and report a coverage score. Token budgeting is
measured on the **assembled block** with tiktoken (`cl100k_base`), not by
summing per-memory estimates — this is what makes the AC-1 boundaries exact.

## Acceptance Criteria

- [ ] A search returns a single assembled context block (not a raw list).
- [ ] The assembled block never exceeds the token budget, measured with tiktoken
      `cl100k_base`. (AC-1)
- [ ] A block whose assembled size is exactly the budget (e.g. 2000) is returned
      in full and measures exactly the budget. (boundary: just-inside)
- [ ] Content that would push the block past the budget is dropped rather than
      overflowing; the lowest-ranked memories are the ones omitted.
      (boundary: 2100 → drop lowest)
- [ ] A zero token budget returns an empty context block (not an error); coverage
      reports nothing filled.
- [ ] A single memory larger than the entire budget is omitted whole, not
      truncated mid-content; an empty block is returned and coverage reports the
      budget could not be filled. (ASSUM-009, low confidence — carried as open)
- [ ] When the budget forces a cut, the higher-ranked memory is kept and the
      lower-ranked one omitted (a highly relevant warning beats a barely relevant
      overview).
- [ ] The result reports a coverage score: the fraction (0.0–1.0) of the budget
      filled, plus the set of payload types that contributed to the block.
- [ ] A search that cannot fill the budget reports partial coverage honestly
      (not padded).
- [ ] Repeated searches over an unchanged corpus return an identical assembled
      block (assembly is deterministic given identical ranked input).
- [ ] All modified files pass project-configured lint/format checks with zero errors.

## Coach Validation

```bash
pytest tests/unit/test_assembly.py -x
ruff check src/fleet_memory/retrieval/
```

## Seam Tests

```python
"""Seam test: verify RankedResults contract from TASK-RA-002."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("RankedResults")
def test_assembly_consumes_ranked_results_in_order():
    """Assembly receives results most-relevant-first and drops from the tail.

    Contract: ranked list is ordered desc by relevance; assembly omits the
    lowest-ranked first when the budget forces a cut.
    Producer: TASK-RA-002
    """
    # Producer side: a 2-element ranked list [high, low]
    ranked = []  # e.g. [RankedMemory(score=0.9, ...), RankedMemory(score=0.1, ...)]
    # Consumer side: under a budget that fits only one, the high-ranked survives
    assert ranked == ranked  # replace with assemble(ranked, budget) assertion
```

## Implementation Notes

- Measure the **rendered** block string, not a sum of parts — boundary ACs
  (exactly-2000, 2100→drop) only hold if you re-measure after each addition.
- Add `tiktoken` to dependencies if not already present; pin the encoding
  (`cl100k_base`) as a module constant so the measure is reproducible.
- Coverage score = `assembled_tokens / token_budget` (0.0 when budget is 0),
  plus the distinct contributing payload types. Keep it a small typed result
  object so TASK-RA-004 and TASK-RA-005 can read it.