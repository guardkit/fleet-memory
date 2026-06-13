---
id: TASK-RA-006
title: Unit, security, and concurrency test suite
task_type: testing
parent_review: TASK-REV-RA05
feature_id: FEAT-MEM-05
wave: 5
implementation_mode: task-work
complexity: 4
dependencies:
- TASK-RA-004
- TASK-RA-005
status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-05
  base_branch: main
  started_at: '2026-06-13T17:25:11.542622'
  last_updated: '2026-06-13T17:36:05.220374'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T17:25:11.542622'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Unit, security, and concurrency test suite

## Description

Hermetic unit coverage for the whole retrieval surface using the fake embed
function (no network, no real store). Covers validation, ranking/filtering,
budgeted assembly boundaries, composition bands, the harness gate, plus the
security/injection and concurrency/determinism regression scenarios.

## Acceptance Criteria

- [ ] Unit tests run with a fake embed function and require no NAS/network.
- [ ] Validation rejections covered: hyphen project, unknown payload type,
      malformed domain tag, negative budget, empty (no query + no filter) request.
- [ ] Filtering/ranking covered: payload-type filter (0/1/3), domain-tag filter,
      cosine-desc ordering, supersession exclusion + include_superseded marking.
- [ ] Budget boundaries covered: exactly-budget, 2100→drop-lowest, zero budget,
      memory-larger-than-budget omitted whole, partial-coverage honesty.
- [ ] Security/injection covered: query text resembling a filter is search-text
      only and still excludes superseded; injection domain tag is rejected.
- [ ] Concurrency/determinism covered (regression): equal-relevance deterministic
      ordering, supersede-mid-search resolves to one state, repeated concurrent
      searches over an unchanged corpus return identical blocks.
- [ ] Degradation covered: embed unavailable and store unreachable both fail
      cleanly with credential-free messages.

## Coach Validation

```bash
pytest tests/unit -x
```

## Implementation Notes

- Use the existing fake-embed fixture pattern from the FEAT-MEM-01/03 unit suites
  (`make_fake_embed(768)`); do not stand up a real store.
- This task asserts behaviour built by TASK-RA-001..005; if a scenario can only
  be proven against a real store/embed, leave it to TASK-RA-007 (integration).
