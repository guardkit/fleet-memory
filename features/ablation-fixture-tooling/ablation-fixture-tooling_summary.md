# Feature Spec Summary: Ablation Fixture Tooling (FEAT-ABL-005)

**Stack**: python
**Generated**: 2026-07-03T12:00:00Z
**Scenarios**: 17 total (5 smoke, 3 regression)
**Assumptions**: 8 total (4 high / 4 medium / 0 low confidence)
**Review required**: No

## Scope

Fixture tooling for the memory-value ablation (scope §4 FEAT-ABL-005): a
pg_dump-based snapshot of the live fleet-memory store into a versioned,
content-hashed fixture; restore into a per-run Postgres; a per-task temporal-cut
filter driven by `episode_meta.occurred_at` (never row `created_at`, which is
backfill-era) that excludes entries with `occurred_at` >= the task's FEAT start
date and all entries with NULL `occurred_at`; and a per-rollout scratch
namespace for rollout-time writes, discarded per rollout. New code is confined
to `scripts/fixture_snapshot.py` and `src/fleet_memory/fixture/` — the
store/retrieval stack is the ablation's subject and stays untouched (scope §7).

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 5 |
| Boundary conditions (@boundary) | 4 |
| Negative cases (@negative) | 5 |
| Edge cases (@edge-case) | 4 |

(One scenario is tagged both @boundary and @negative; counts overlap.)

## Acceptance anchors (scope §4 / build-plan Step 2)

- Hash stability: "The same fixture id yields a byte-identical corpus on every
  restore" (restore → re-snapshot → byte-identical, hash equal).
- Answer-key exclusion: "The FEAT-HARV cut excludes the post-FEAT smoke outcome
  and every untimestamped entry" — the cut for a 2026-06-25 task demonstrably
  excludes the OUT-SMOKE build_outcome (occurred_at 2026-06-29) and all
  null-timestamped entries; on fixture v1 the null-exclusion count must equal
  the fixture's recorded count (176 verified on the live store 2026-07-03).
- Read-only source: "Snapshotting never modifies the source store" (P3: the
  live store is used read-only, snapshot only).

## Deferred Items

None. Phase 4 edge-case expansion declined: concurrent-rollout isolation is
structural (one per-run Postgres per rollout; Harbor runs a fresh container per
rollout), and cross-rollout scratch leakage is already covered.

## Open Assumptions (low confidence)

None. Curation and assumption resolution performed autonomously against
scope §4 acceptance and build-plan Step 2 (2026-07-03); medium-confidence
assumptions (hash algorithm, fixture location, scratch namespace shape,
per-run deployment) are flagged for Coach review during implementation.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Ablation Fixture Tooling" \
      --context features/ablation-fixture-tooling/ablation-fixture-tooling_summary.md
