# Feature: Ablation Fixture Tooling (FEAT-ABL-005)

Fixture tooling for the memory-value ablation (phase ABL, build-plan Step 2):
pg_dump-based versioned snapshots of the live fleet-memory store with a
content hash (same fixture id ⇒ byte-identical retrieval corpus), restore
into per-run Postgres, a per-task temporal cut on `episode_meta.occurred_at`
(excluding `>=` the task's FEAT start date and all NULL-timestamped entries —
answer-key leakage control), and a per-rollout scratch namespace for
rollout-time writes.

- Feature YAML: `.guardkit/features/FEAT-ABL-005.yaml`
- Review record: `tasks/completed/TASK-REV-ABL5-plan-ablation-fixture-tooling.md`
- Feature spec (BDD): `features/ablation-fixture-tooling/`
- Guide: `IMPLEMENTATION-GUIDE.md` (diagrams + §4 integration contracts)

## Tasks

| ID | Title | Wave | Cx | Deps |
|----|-------|------|----|------|
| TASK-ABL5-001 | Fixture package scaffolding - manifest, content hash, error taxonomy | 1 | 4 | — |
| TASK-ABL5-002 | Deterministic pg_dump snapshot and hash-verified restore | 2 | 6 | 001 |
| TASK-ABL5-003 | Per-task temporal-cut filter on episode_meta.occurred_at | 2 | 5 | 001 |
| TASK-ABL5-004 | Scratch namespace lifecycle for rollout-time writes | 2 | 4 | 001 |
| TASK-ABL5-005 | Fixture CLI entrypoint scripts/fixture_snapshot.py | 3 | 4 | 002,003,004 |
| TASK-ABL5-006 | Seeded-store acceptance tests - byte-identity, FEAT-HARV cut, scratch isolation | 4 | 5 | 002–005 |

## Acceptance (scope §4 / build plan)

1. Hash stability: restore → re-snapshot is byte-identical (same content hash).
2. The cut for a 2026-06-25 task (FEAT-HARV) demonstrably excludes the
   OUT-SMOKE build_outcome (occurred_at 2026-06-29) and all null-timestamped
   entries; on fixture v1 the null-exclusion count == 176.
3. Rollout writes are scratch-isolated and discarded per rollout.
4. The live store is only ever read (read-only snapshot session); unit tests
   run against seeded local copies.
