---
id: TASK-RIP-011
title: "Operator run: full guardkit corpus re-index verification"
status: backlog
created: 2026-06-13 20:30:00+00:00
updated: 2026-06-13 20:30:00+00:00
priority: high
task_type: operator_handoff
parent_review: TASK-REV-RIP7
feature_id: FEAT-MEM-07
wave: 8
implementation_mode: direct
complexity: 3
estimated_minutes: 45
dependencies:
- TASK-RIP-009
- TASK-RIP-010
tags:
- reindex
- operator-handoff
- verification
- live-infra
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Operator run — full guardkit corpus re-index verification

## Description

Operator-run verification of the FEAT-MEM-07 acceptance criteria that AutoBuild's
Player ↔ Coach loop **cannot satisfy by construction** — they are runtime
observations against the *live* relay + NAS Postgres + real embeddings over the
*actual* guardkit corpus, with a wall-clock bound. The implementation logic these
ACs exercise is fully unit/integration-tested in TASK-RIP-004/005/007/010 against
ephemeral infrastructure; this task is the live confirmation only.

Run from the Mac against the live stack:

```bash
python -m fleet_memory.reindex            # full corpus re-index
python -m fleet_memory.reindex --audit    # stream-vs-store audit (TASK-RIP-007)
python -m fleet_memory.reindex --parity   # probe-set parity report (TASK-RIP-008)
python -m fleet_memory.reindex            # second run — confirm no-op
```

## Required operator follow-up

This task is `task_type: operator_handoff` — AutoBuild will not attempt it. The
operator must verify the runtime acceptance criteria below manually, then mark the
task complete via `/task-complete`.

- **AC-1a**: A full guardkit corpus re-index completes in under five minutes
  (wall-clock, live relay + NAS Postgres + real embeddings).
- **AC-1b**: The full re-index run makes zero language-model / cloud / frontier-model
  calls (confirm via config/grep + egress observation).
- **AC-1c**: A second run over the unchanged corpus is a no-op — no stored record
  created or modified.
- **AC-3**: The stream-vs-store audit reports 100% accounted (every published
  episode stored or dead-lettered).
- **AC-4**: The probe-set parity report is generated against the re-indexed corpus
  and meets the parity bar agreed for FEAT-MEM-05 (record the figure).

## BDD Scenarios Covered

- "A full guardkit corpus re-index completes within the time budget"
- "A full re-index run makes no language-model call" (live confirmation)
- "A second run over an unchanged corpus leaves the store unchanged" (live confirmation)

## Implementation Notes

- This mirrors the FEAT-MEM-01 NAS-deploy operator handoff (TASK-MEM-008): the
  artifacts are ready, the operator runs them against live infrastructure and
  records the result.
- Attach the audit JSON and parity report to the task on completion as the
  verification record.
