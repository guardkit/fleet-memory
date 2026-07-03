---
id: TASK-ABL5-006
title: Seeded-store acceptance tests - byte-identity, FEAT-HARV cut, scratch isolation
task_type: testing
parent_review: TASK-REV-ABL5
feature_id: FEAT-ABL-005
wave: 4
implementation_mode: task-work
complexity: 5
dependencies:
- TASK-ABL5-002
- TASK-ABL5-003
- TASK-ABL5-004
- TASK-ABL5-005
status: pending
tags:
- ablation
- fixture
- integration-tests
- fleet-memory
consumer_context:
- task: TASK-ABL5-002
  consumes: fixture archive layout + create_snapshot/restore_fixture
  framework: fleet_memory.fixture
  driver: Python API
  format_note: "restore -> re-snapshot must reproduce byte-identical payload files (same content hash)"
- task: TASK-ABL5-003
  consumes: apply_temporal_cut / CutResult
  framework: fleet_memory.fixture.temporal_cut
  driver: Python API
  format_note: "excluded_null on the seeded copy must equal the manifest's null_occurred_at_count"
- task: TASK-ABL5-004
  consumes: scratch_namespace / discard_scratch
  framework: fleet_memory.fixture.scratch
  driver: Python API
  format_note: discard removes only the exact scratch project; corpus rows untouched
---

# Task: Seeded-store acceptance tests - byte-identity, FEAT-HARV cut, scratch isolation

## Description

The feature's acceptance proof, as executable tests: a new integration test
module `tests/integration/test_fixture_acceptance.py` marked
`@pytest.mark.integration` (deselected from the default suite; run
explicitly), built on the existing `ephemeral_pg` fixture
(`tests/integration/conftest.py` — ephemeral Docker pgvector Postgres, one
isolated instance per session). **These tests run against seeded local
copies only — never the live store** (build-plan Step 2 validation rule).

### Seeding helper

Seed a "store copy" into an ephemeral database the same way production data
got there: `async_store_context` with the `fake_embed` fixture (root
`tests/conftest.py`, 768 dims) and `store.aput` of values shaped like the
deterministic writer's output (`content`, `content_hash`, `version`,
`payload_type`, `natural_key`, `project`, `identifier`, `episode_type`,
`episode_meta`) — see `src/fleet_memory/writer/core.py:187-205`. The seed set
(project `guardkit`, mirroring the live-store shape verified in scope §2):

- `build_outcome:guardkit:OUT-SMOKE` with
  `episode_meta.occurred_at = "2026-06-29T00:00:00+00:00"` — the known
  post-FEAT entry the acceptance names
- a FEAT-HARV-era chunk with `occurred_at = "2026-06-24T12:00:00+00:00"`
  (must survive the cut)
- a boundary entry with `occurred_at = "2026-06-25T00:00:00+00:00"`
  (must be excluded — `>=` semantics)
- an old-work/backfill entry with `occurred_at = "2026-05-01T09:00:00+00:00"`
  (survives; its row `created_at` is "now", i.e. backfill-era — proving
  `created_at` is not the axis)
- N entries with NULL/absent `occurred_at` (mix of: `occurred_at: None`,
  `episode_meta` without the key, and no `episode_meta` at all) — all must
  be excluded; N is whatever the seed defines (e.g. 5) and MUST equal the
  manifest's `null_occurred_at_count` after snapshot

### Required tests (each maps to a spec acceptance anchor)

1. **Round-trip byte-identity (hash stability)**: seed DB A -> `create_snapshot`
   (fixture `v1t`, tmp fixtures root) -> `restore_fixture` into fresh DB B ->
   `create_snapshot` from B (fixture `v1t_rt`) -> assert every payload file
   byte-identical and `content_hash` equal. This is "same fixture id =>
   byte-identical retrieval corpus".
2. **FEAT-HARV cut proof**: restore `v1t` into a fresh DB ->
   `apply_temporal_cut(dsn, date(2026, 6, 25))` -> assert:
   - `build_outcome:guardkit:OUT-SMOKE` row absent
   - every NULL-`occurred_at` entry absent and
     `result.excluded_null == manifest.null_occurred_at_count`
   - the 2026-06-24 chunk and the 2026-05-01 entry still present
   - the 2026-06-25T00:00:00Z boundary entry absent
   - no orphaned `store_vectors` rows
     (`SELECT count(*) FROM store_vectors sv LEFT JOIN store s USING (prefix, key) WHERE s.key IS NULL` == 0)
   - re-applying the cut returns `CutResult(0, 0, remaining)`
3. **Restore refusals**: unknown fixture id raises `UnknownFixtureError`;
   tampering one byte of a payload file raises `FixtureHashMismatchError`;
   restoring onto a non-empty DB raises `FixtureError`.
4. **Scratch isolation**: on a restored DB, `aput` entries under
   `scratch_namespace("run_01", "build_outcome")` -> corpus row count
   unchanged outside scratch; retrieval-shaped prefix listing for project
   `guardkit` does not see scratch rows; `discard_scratch(dsn, "run_01")`
   removes them (and their vectors) and a second discard returns 0; a
   sibling `scratch_run_02` namespace survives run_01's discard.
5. **Source read-only**: after `create_snapshot` against the seeded source,
   the source row set is unchanged (count + max(updated_at) stable).

## Acceptance Criteria

- [ ] All five test groups implemented in `tests/integration/test_fixture_acceptance.py`, marked `integration`, using `ephemeral_pg` + `fake_embed` (no live store, no real embedding service, no network beyond local Docker)
- [ ] Round-trip test asserts byte-identical payload files AND equal content hashes
- [ ] FEAT-HARV test asserts OUT-SMOKE exclusion, total null exclusion with count == manifest count, boundary exclusion, pre-cut retention, vector consistency, idempotency
- [ ] The default suite (`pytest tests/ -m "not integration"`) still passes with zero new failures
- [ ] `pytest tests/integration/test_fixture_acceptance.py -m integration` passes locally (requires Docker; document the command in the module docstring)
- [ ] No changes outside `tests/` (and none to existing store/retrieval code)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

This task IS the test suite. Keep per-test runtime sane: one ephemeral
Postgres session, fresh **databases** per test via `CREATE DATABASE` on the
ephemeral instance (or separate schemas) rather than one container per test
— follow the existing integration-suite patterns.

## Implementation Notes

- `pytest-asyncio` patterns for the async store seeding are already used by
  the existing integration tests — mirror them.
- The seeded null-count (e.g. 5) deliberately differs from the live 176: the
  tooling records the count per snapshot; the "== 176" check is a fixture-v1
  property verified during feature validation against the real snapshot, not
  in CI.
