---
id: TASK-RIP-007
title: Stream-vs-store audit script (100% accounted)
status: backlog
created: 2026-06-13 20:30:00+00:00
updated: 2026-06-13 20:30:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-RIP7
feature_id: FEAT-MEM-07
wave: 5
implementation_mode: task-work
complexity: 5
estimated_minutes: 75
dependencies:
- TASK-RIP-005
tags:
- reindex
- audit
- accounting
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Stream-vs-store audit script (100% accounted)

## Description

After a run, audit the published episodes against the store: **every published
episode must be either stored (writer committed) or recorded on the dead-letter
subject** — none unaccounted. This is FEAT-MEM-07 AC-3 and the "no episode is
unaccounted for" invariant. The audit consumes the `RunReport` from TASK-RIP-005
(the set of published natural keys) and reconciles it against stored records and
DLQ records.

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/audit.py` reconciles published episodes against stored records and dead-letter records
- [ ] Every published episode is classified as **stored** or **dead-lettered**
- [ ] Any episode that is neither stored nor dead-lettered is reported as a failure (non-zero audit exit / explicit unaccounted list)
- [ ] A clean full-corpus run reports 100% accounted
- [ ] `tests/unit/reindex/test_audit.py` (and/or an integration test) covers: a seeded store where all episodes are stored → 100%; one poison episode on DLQ → still accounted; a missing record → reported unaccounted
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_audit.py::test_all_stored_reports_100_percent`
- [ ] `test_audit.py::test_dlq_episode_counts_as_accounted`
- [ ] `test_audit.py::test_missing_record_reported_unaccounted`

## BDD Scenarios Covered

- "After a run every published episode is accounted for as ingested or dead-lettered"

## Implementation Notes

- Source the "published" set from the `RunReport` natural keys (TASK-RIP-005);
  resolve store presence via `record_identity(natural_key)`
  ([src/fleet_memory/writer/identity.py](src/fleet_memory/writer/identity.py)) against the store.
- DLQ membership comes from the relay's dead-letter subject (see
  [src/fleet_memory/relay/handler.py](src/fleet_memory/relay/handler.py) `dlq_subject`).
- Keep the audit read-only — it observes, it never writes or republishes.
