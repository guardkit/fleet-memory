---
id: TASK-REV-RLY04
title: "Plan: Relay Integration"
task_type: review
priority: high
status: review_complete
feature_ref: FEAT-MEM-04
context_sources:
  - features/relay-integration/relay-integration_summary.md
  - features/relay-integration/relay-integration.feature
  - features/relay-integration/relay-integration_assumptions.yaml
clarification:
  context_a:
    decisions:
      focus: architecture_correctness
      tradeoff: quality
      assumptions: plan_with_assumptions_plus_verify_task
---

# Task: Plan: Relay Integration (FEAT-MEM-04)

## Description

Decision review for the relay consumer: a FastStream durable consumer on the
MEMORY stream that ingests `MemoryEpisodeV1` envelopes, routes them by
`content_format` (structured JSON → registry → deterministic writer; markdown/
text → heading-aware chunk → embed → store), acknowledges only after a durable
commit, and parks poison episodes on a dead-letter subject. Two-layer
idempotency makes at-least-once redelivery inert. No language model on the
write path.

See `.claude/reviews/TASK-REV-RLY04-review-report.md` for the full analysis.
