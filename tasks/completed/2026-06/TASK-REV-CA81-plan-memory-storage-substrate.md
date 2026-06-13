---
id: TASK-REV-CA81
title: "Plan: Memory Storage Substrate"
status: completed
created: 2026-06-12T16:30:00Z
updated: 2026-06-12T18:15:00Z
decision: implement
feature_created: FEAT-CA81
review_results:
  mode: decision
  depth: standard
  findings_count: 6
  recommendations_count: 13
  decision_axes: 5
  report_path: .claude/reviews/TASK-REV-CA81-review-report.md
  completed_at: 2026-06-12T16:50:00Z
priority: high
task_type: review
tags: [feature-planning, storage, pgvector, infrastructure, hermetic-testing]
complexity: 7
review_mode: decision
review_depth: standard
context_files:
  - features/storage-substrate/storage-substrate_summary.md
  - features/storage-substrate/storage-substrate.feature
  - features/storage-substrate/storage-substrate_assumptions.yaml
  - docs/research/ideas/phase-core-build-plan.md
  - docs/runbooks/RUNBOOK-nas-postgres-deploy.md
clarification:
  context_a:
    timestamp: 2026-06-12T16:29:00Z
    decisions:
      focus: all
      tradeoff: hermetic_correctness
      assumptions: defaults_plus_verify
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Plan: Memory Storage Substrate

## Description

Decision-mode review for FEAT-MEM-01 (Phase CORE build plan): the storage substrate
for fleet-memory. LangGraph `AsyncPostgresStore` on Postgres 16 + pgvector with a
768-dimension nomic-embed-text-v1.5 embed function served by llama-swap on GB10
(:9000). Two deployment targets — `deploy/local/` (ephemeral, random-port, throwaway
instance used by ALL automated test gates including AutoBuild) and `deploy/nas/`
(durable shared instance on the Synology NAS; backed-up volume, 5432 LAN/Tailscale
only). Store semantics (put/get/delete/semantic search with metadata filters),
lifespan-managed connection pool, pydantic-settings profile configuration, and the
three-tier test strategy (fake-embed unit tests, marker-gated integration tests
against the ephemeral instance, one documented smoke against the NAS productizing
runbook gates G2–G5).

The BDD spec already exists: 34 scenarios at `features/storage-substrate/storage-substrate.feature`.

## Review Scope (Context A clarification)

- **Focus**: All areas — balanced coverage across hermetic test infrastructure,
  store semantics, lifespan/pool wiring, settings profiles, NAS security boundary,
  and scaffolding (repo currently has NO Python scaffolding).
- **Trade-off priority**: Hermetic correctness — deploy/local isolation provably
  right (random ports, parallel-worktree safety, aborted-run cleanup). The AC makes
  this the explicit pass/fail gate: full suite passes with the NAS powered off.
- **Low-confidence assumptions** (ASSUM-004 pool=10/queue, ASSUM-006 fail-fast 10s,
  ASSUM-008 embed timeout 10s): use as defaults; implementation verifies against
  asyncpg-pool/httpx/AsyncPostgresStore actuals and may revise with recorded
  reasoning — no spec amendment needed.

## Acceptance Criteria (from build plan FEAT-MEM-01)

- [ ] `store.aput` / `asearch` round-trip with real nomic embeddings against the ephemeral instance
- [ ] Full test suite passes on the MacBook with the NAS powered off (hermeticity proven)
- [ ] NAS instance deployed via the runbook's scripted path (`deploy.sh`); `smoke.sh` (G2–G5) passes from the Mac
- [ ] Vector index created at 768 dims; search returns by similarity with metadata filter
- [ ] No hyphens in any Postgres identifier; namespace tuples use underscores
- [ ] Connection pool opens/closes cleanly under lifespan; settings via env only

## Review Findings

[Populated by /task-review]
