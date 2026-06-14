---
complexity: 5
created: 2026-06-13 20:30:00+00:00
dependencies:
- TASK-RIP-001
estimated_minutes: 60
feature_id: FEAT-MEM-07
id: TASK-RIP-003
implementation_mode: task-work
parent_review: TASK-REV-RIP7
priority: high
status: design_approved
tags:
- reindex
- parsing
- classification
- accounting
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: Front-matter reader + document-kind classifier + parser dispatch
updated: 2026-06-13 20:30:00+00:00
wave: 2
---

# Task: Front-matter reader + document-kind classifier + parser dispatch

## Description

Read YAML front-matter from a corpus document and classify its document kind —
seed module / ADR / review report / completed-task outcome — **deterministically**
from path conventions plus front-matter fields, then dispatch to the right parser.
Unrecognized kinds and malformed front-matter are **reported with a reason, never
guessed at and never silently dropped** (ASSUM-004, the no-silent-loss invariant).

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/classify.py` reads front-matter and returns a document kind or an explicit `unrecognized` outcome
- [ ] Classification is deterministic (no LLM): derived from path/house-format conventions and front-matter fields only
- [ ] A document whose front-matter cannot be parsed yields a structured parse-failure result carrying a human-readable reason (it does not raise an exception that aborts the run)
- [ ] A document matching none of the four known kinds yields an `unrecognized` result with a reason
- [ ] A dispatch table maps each known kind to its parser callable (the parsers themselves land in TASK-RIP-004)
- [ ] `tests/unit/reindex/test_classify.py` covers malformed front-matter and unrecognized-kind paths
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_classify.py::test_malformed_frontmatter_reports_reason`
- [ ] `test_classify.py::test_unrecognized_kind_reported`
- [ ] `test_classify.py::test_each_known_kind_dispatches_to_a_parser`

## BDD Scenarios Covered

- "A document with malformed front-matter is reported and skipped"
- "A document matching no known parser is recorded as unrecognized"

## Implementation Notes

- Keep a single `ParseResult` shape (a tagged union: `parsed` | `parse_failure` |
  `unrecognized`, each carrying the source ref and, on failure, a reason) so the
  orchestrator (TASK-RIP-005) can account for every document uniformly.
- Front-matter parsing should tolerate a missing front-matter block as "unrecognized"
  rather than crashing.
- Do not publish or construct payloads here — this task only classifies and routes.