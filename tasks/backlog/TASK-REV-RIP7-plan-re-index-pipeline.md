---
id: TASK-REV-RIP7
title: "Plan: Re-index Pipeline"
task_type: review
priority: high
status: in_review
feature_ref: FEAT-MEM-07
context_files:
  - features/re-index-pipeline/re-index-pipeline_summary.md
  - features/re-index-pipeline/re-index-pipeline.feature
  - features/re-index-pipeline/re-index-pipeline_assumptions.yaml
clarification:
  context_a:
    decisions:
      focus: all
      tradeoff: quality
---

# Plan: Re-index Pipeline (FEAT-MEM-07, part a + b)

Decision-mode review for the deterministic re-index pipeline that walks
guardkit's authoritative markdown corpus, parses each document into a typed
payload, and publishes it as a `MemoryEpisodeV1` (`content_format="json"` +
explicit `payload_type`) through the live relay (FEAT-MEM-04) into the
deterministic writer (FEAT-MEM-03). Part (b) adds a reviewed backfill staging
gate for Fable-authored payloads.

See the analysis and decision options recorded by `/feature-plan`.
