---
id: TASK-MEM-013
title: Assumption verification record
status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: documentation
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 8
implementation_mode: direct
complexity: 1
estimated_minutes: 20
dependencies:
- TASK-MEM-009
- TASK-MEM-010
- TASK-MEM-011
- TASK-MEM-012
tags:
- assumptions
- documentation
- verification
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T23:06:02.638795'
  last_updated: '2026-06-12T23:11:22.926887'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T23:06:02.638795'
    player_summary: Updated assumptions YAML file with verified values from measurement
      tasks (TASK-MEM-003, TASK-MEM-006, TASK-MEM-010, TASK-MEM-011). All verified
      values matched their placeholders (10/10s/10s), so no settings.py or .env.example
      updates were needed per AC-005. Created comprehensive test suite to validate
      the verification records.
    player_success: true
    coach_success: true
---

# Task: Assumption verification record

## Description

Close the loop on the three low-confidence spec assumptions (Context A decision:
defaults + verify). The test tasks measured the actual behaviour; this task
records the verified values in `storage-substrate_assumptions.yaml` and aligns
`settings.py` defaults if any verified value differs from its placeholder.

## Acceptance Criteria

- [ ] ASSUM-004 entry updated with a `verified_value` field recording the actual psycopg-pool overflow behaviour observed in TASK-MEM-010 (queue vs timeout, and at what bound)
- [ ] ASSUM-006 entry updated with `verified_value` recording the actual connect-timeout behaviour observed in TASK-MEM-006/010 against a closed port
- [ ] ASSUM-008 entry updated with `verified_value` recording the actual httpx read-timeout behaviour observed in TASK-MEM-003
- [ ] Each updated entry: `confidence` changed from `low` to `verified`, plus a `verified_by_task` field naming the measuring task
- [ ] If any verified value differs from its placeholder (10 / 10s / 10s), the corresponding `settings.py` default and `.env.example` comment are updated in the same commit, with the reasoning recorded in the assumption entry
- [ ] `python -c "import yaml; d = yaml.safe_load(open('features/storage-substrate/storage-substrate_assumptions.yaml')); assert all(a.get('confidence') != 'low' for a in d['assumptions'])"` exits 0
- [ ] If TASK-MEM-011 found a non-10 default search limit (ASSUM-002), record it the same way

## Test Requirements

- [ ] None beyond the YAML sanity check — this is a documentation task

## BDD Scenarios Covered

- "Operations beyond pool capacity queue rather than fail" (ASSUM-004 recorded)
- "The service refuses to start when the database is unreachable" (ASSUM-006 recorded)
- "A hung embedding service cannot stall store operations indefinitely" (ASSUM-008 recorded)

## Implementation Notes

- Source measurements from the test-file comments the earlier tasks were required to leave (TASK-MEM-003 AC3, TASK-MEM-006 AC3, TASK-MEM-010 AC5/AC6, TASK-MEM-011 AC2)
- Spec-amendment-free by design: Context A chose "defaults + verify", so revisions here need recorded reasoning, not a new spec round
