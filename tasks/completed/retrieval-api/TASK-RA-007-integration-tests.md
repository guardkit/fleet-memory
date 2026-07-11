---
id: TASK-RA-007
title: Marker-gated integration tests against real store and embed
task_type: testing
parent_review: TASK-REV-RA05
feature_id: FEAT-MEM-05
wave: 5
implementation_mode: task-work
complexity: 4
dependencies:
- TASK-RA-004
- TASK-RA-005
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-MEM-05 completed"
pre_sweep_status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-05
  base_branch: main
  started_at: '2026-06-13T17:25:11.542303'
  last_updated: '2026-06-13T17:36:04.716535'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T17:25:11.542303'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Marker-gated integration tests against real store and embed

## Description

`@pytest.mark.integration` tests that exercise the full retrieval path against
an ephemeral Postgres 16 + pgvector instance (deploy/local) with real nomic
embeddings over Tailscale. Proves the search→assembly→coverage path round-trips
against real vectors, and that the probe-set harness runs end-to-end.

## Acceptance Criteria

- [ ] Integration tests are marker-gated (`@pytest.mark.integration`) and
      excluded from the hermetic unit gate.
- [ ] A populated ephemeral store + real embed returns project-scoped,
      cosine-ranked results for a real query.
- [ ] Supersession exclusion holds end-to-end against records written by the
      deterministic writer (FEAT-MEM-03).
- [ ] Budgeted assembly stays within budget when measured against a real
      assembled block (AC-1) over real corpus content.
- [ ] The probe-set harness runs the frozen query set against the real
      (re-indexed) corpus and emits a parity report.
- [ ] Tests use a throwaway, random-port instance (no NAS dependency).

## Coach Validation

```bash
pytest tests/integration -m integration -x
```

## Implementation Notes

- Follow the FEAT-MEM-01 integration pattern: ephemeral `pgvector/pgvector:pg16`
  via `deploy/local/`, random port from env, real embed at llama-swap `:9000`
  over Tailscale.
- The p95 < 200ms latency AC is a performance gate for the probe harness, not a
  behavioural assertion here — out of scope for this feature per the spec.
