---
id: TASK-REV-ABL5
title: "Plan: Ablation Fixture Tooling (FEAT-ABL-005)"
task_type: review
priority: high
status: completed
created: 2026-07-03
completed: 2026-07-03
feature_id: FEAT-ABL-005
clarification:
  context_a:
    timestamp: 2026-07-03T12:10:00Z
    mode: autonomous (build-plan Step 2; reviewer = executing agent)
    decisions:
      focus: technical+architecture
      tradeoff: quality
      concerns: "answer-key leakage (scope §3.3), retrieval stack untouched (scope §7), live store read-only (P3)"
  context_b:
    timestamp: 2026-07-03T12:10:00Z
    decisions:
      approach: option_1_python_package_plus_cli
      execution: parallel (wave 2 has 3 independent tasks)
      testing: standard (unit per task + integration acceptance task)
---

# Review: Plan Ablation Fixture Tooling (FEAT-ABL-005)

Feature spec: `features/ablation-fixture-tooling/` (17 scenarios, 8 assumptions,
0 low-confidence). Source: build-plan Step 2 verbatim spec text; scope §4
FEAT-ABL-005 acceptance.

## Options analysed

**Option 1 (RECOMMENDED): Python package + thin CLI.**
`src/fleet_memory/fixture/` (manifest/hash, snapshot, restore, temporal cut,
scratch namespace) + `scripts/fixture_snapshot.py` argparse CLI. pg_dump for
schema; data exported with deterministic ordering (ORDER BY primary key) so
restore -> re-snapshot is byte-identical; SHA-256 content hash in a JSON
manifest; temporal cut = SQL deletion in the restored per-run store (never a
retrieval-time filter); scratch namespace = per-rollout project segment.
Complexity 6/10. Pros: unit-testable seams, credential hygiene reusable,
matches the build-plan files table exactly, zero changes to the
store/retrieval stack (scope §7). Cons: subprocess seams to pg_dump/psql need
careful mocking.

**Option 2: Shell scripts around pg_dump/pg_restore.** Rejected — no
unit-testability, no manifest/hash discipline, error handling and credential
hygiene ad hoc.

**Option 3: Store-API JSONL export/import.** Rejected — violates the spec's
"pg_dump-based" requirement; loses schema fidelity and pgvector embeddings
(re-embedding would break byte-identity and cost GPU time).

## Decision

[I]mplement Option 1. 6 tasks, 4 waves (see IMPLEMENTATION-GUIDE.md in
`tasks/backlog/ablation-fixture-tooling/`). Constraints carried into every
task: new code ONLY in `scripts/fixture_snapshot.py` + `src/fleet_memory/fixture/`;
live store is read-only source (P3); unit suite (620 passed / 2 skipped at
HEAD) stays green; DB-dependent acceptance tests are `-m integration` against
the existing `ephemeral_pg` fixture, never the live store.
