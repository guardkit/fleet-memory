---
id: TASK-REV-RA05
title: "Plan: Retrieval API + Context Assembly"
task_type: review
priority: high
status: review_complete
feature_ref: FEAT-MEM-05
context_sources:
  - features/retrieval-api/retrieval-api_summary.md
  - features/retrieval-api/retrieval-api.feature
  - features/retrieval-api/retrieval-api_assumptions.yaml
clarification:
  context_a:
    decisions:
      focus: all
      tradeoff: quality
---

# Task: Plan: Retrieval API + Context Assembly (FEAT-MEM-05)

## Description

Decision review for the read-path counterpart to the deterministic writer
(FEAT-MEM-03). A single service entry point
`search(project, payload_types, domain_tags, query, token_budget, include_superseded=False)`
performs a filtered, vector-ranked, token-budgeted retrieval over typed
fleet-memory records and assembles a single context block. It excludes
superseded records by default, ports guardkit's job-specific context
composition by complexity band, and reports a coverage score. A probe-set
evaluation harness backs the ≥15-query retrieval-parity gate (AC-3), flagging
divergence against recorded Graphiti baselines.

See `.claude/reviews/TASK-REV-RA05-review-report.md` for the full analysis.
