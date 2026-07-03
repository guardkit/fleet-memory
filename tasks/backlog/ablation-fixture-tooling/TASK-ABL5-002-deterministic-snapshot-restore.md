---
id: TASK-ABL5-002
title: Deterministic pg_dump snapshot and hash-verified restore
task_type: feature
parent_review: TASK-REV-ABL5
feature_id: FEAT-ABL-005
wave: 2
implementation_mode: task-work
complexity: 6
dependencies:
- TASK-ABL5-001
status: pending
tags:
- ablation
- fixture
- pg-dump
- fleet-memory
consumer_context:
- task: TASK-ABL5-001
  consumes: FixtureManifest
  framework: Pydantic v2 model + JSON manifest file
  driver: fleet_memory.fixture.manifest
  format_note: manifest.json with content_hash = SHA-256 over payload files (rel_path + NUL + bytes, sorted); manifest.json itself excluded from the hash; null_occurred_at_count recorded at snapshot time
---

# Task: Deterministic pg_dump snapshot and hash-verified restore

## Description

`src/fleet_memory/fixture/snapshot.py` and
`src/fleet_memory/fixture/restore.py`: pg_dump-based snapshot of a
fleet-memory store into a versioned fixture, and restore into a per-run
Postgres. The acceptance bar is **byte-identity**: restoring a fixture into a
fresh database and re-snapshotting it MUST reproduce byte-identical payload
files (same content hash). That drives every design choice below.

### Snapshot — `create_snapshot(source_dsn, fixture_id, fixtures_root) -> FixtureManifest`

Fixture directory layout (producer of the fixture-archive contract):

```
<fixtures_root>/<fixture_id>/
├── manifest.json     # FixtureManifest (TASK-ABL5-001)
├── schema.sql        # pg_dump --schema-only
└── data/<table>.copy # one COPY TEXT-format file per table, deterministic order
```

1. **Schema**: `pg_dump --schema-only --no-owner --no-privileges` via
   subprocess (pass the DSN as an argument list element, never through a
   shell string; never log it). Strip volatile comment lines beginning
   `-- Dumped from database version` / `-- Dumped by pg_dump version` into
   manifest metadata instead, so the schema file is byte-stable across
   dump sessions against equivalent databases.
2. **Data**: psycopg connection with `SET default_transaction_read_only = on`
   and `SET TIME ZONE 'UTC'` (the read-only session makes the P3 "never
   write to the live store" guarantee structural, not behavioural). Discover
   the store tables from `information_schema.tables` (public schema, base
   tables). Expect the langgraph AsyncPostgresStore set — `store`,
   `store_vectors`, and its migrations table(s) (verify the exact names from
   a locally set-up store; include migrations tables so `store.setup()`
   against a restored database is a no-op rather than a re-migration). Fail
   loudly on unexpected extra tables (nothing silently dropped).
   Export each table with
   `COPY (SELECT * FROM <t> ORDER BY <primary key columns>) TO STDOUT`
   (TEXT format) into `data/<t>.copy` — primary-key ordering is what makes
   the dump deterministic regardless of physical row order. Read PK columns
   from the catalog; fail loudly if a table has no PK (cannot guarantee
   determinism).
3. **Null-count metadata**: in the same read-only session, record
   `null_occurred_at_count` = `SELECT count(*) FROM store WHERE (value #>> '{episode_meta,occurred_at}') IS NULL`
   (covers both JSON null and absent key), plus per-table row counts.
4. Write payload files, then `compute_content_hash`, then `manifest.json`
   (TASK-ABL5-001 contract). Refuse to overwrite an existing fixture id
   (versioned fixtures are immutable — a new corpus is a new id).

### Restore — `restore_fixture(fixture_id, target_dsn, fixtures_root) -> FixtureManifest`

1. `read_manifest` (raises `UnknownFixtureError` if absent).
2. Recompute the content hash; on mismatch raise `FixtureHashMismatchError`
   — a corrupted fixture must never grade a rollout.
3. Refuse a non-empty target: if any of the fixture's tables already exist
   in the target database, raise `FixtureError` (per-run stores are fresh by
   contract; silent merge would corrupt the corpus).
4. Apply `schema.sql` (psql subprocess or psycopg execution), then
   `COPY <t> FROM STDIN` each data file in schema-dependency order (store
   before store_vectors — FK), inside a transaction.
5. Return the manifest so callers can log fixture id + hash per rollout.

Credential hygiene throughout: exceptions and logs name `host:port/db` only.

## Acceptance Criteria

- [ ] `create_snapshot` produces `schema.sql`, one `data/<table>.copy` per store table, and a `manifest.json` whose `content_hash` verifies via `compute_content_hash`
- [ ] Snapshot data export runs inside a read-only UTC session (`default_transaction_read_only = on` observable in the session-setup SQL; unit test asserts the SQL/session seam)
- [ ] Snapshot refuses to overwrite an existing fixture id
- [ ] `restore_fixture` on an unknown fixture id raises `UnknownFixtureError`
- [ ] `restore_fixture` on a tampered payload file raises `FixtureHashMismatchError` before touching the target database
- [ ] `restore_fixture` refuses a target that already contains any of the fixture's tables
- [ ] Data files are primary-key ordered (unit test on the generated COPY SELECT statements)
- [ ] No DSN or password ever appears in an exception message or log line
- [ ] New code only under `src/fleet_memory/fixture/` (+ tests)
- [ ] All modified files pass project-configured lint/format checks with zero errors
- [ ] Unit tests green in the default suite (no Docker/Postgres required — subprocess and connection seams injected/mocked)

## Test Requirements

Unit tests in `tests/unit/fixture/test_snapshot.py` and
`tests/unit/fixture/test_restore.py`:
- command/SQL construction (pg_dump argv, ORDER BY clause from PK columns,
  read-only session statements) via injected fake connection/subprocess seams
- refusal paths: existing fixture id, unknown fixture, hash mismatch (build a
  real tmp fixture with TASK-ABL5-001 helpers and flip one byte),
  no-primary-key table, unexpected table
- credential hygiene: errors raised with a password-bearing DSN never contain
  the password

End-to-end byte-identity against a real Postgres belongs to TASK-ABL5-006
(integration-marked), not here.

## Seam Tests

The following seam test validates the integration contract with TASK-ABL5-001.

```python
"""Seam test: verify FixtureManifest contract from TASK-ABL5-001."""
import pytest


@pytest.mark.seam
def test_fixture_manifest_hash_contract(tmp_path):
    """Verify snapshot output hash-verifies via the TASK-ABL5-001 helpers.

    Contract: content_hash = SHA-256 over payload files (rel_path + NUL +
    bytes, sorted by relative path), manifest.json excluded.
    Producer: TASK-ABL5-001
    """
    from fleet_memory.fixture.manifest import compute_content_hash, read_manifest
    # Arrange a snapshot-shaped directory via the snapshot writer seam
    # (payload files + manifest), then:
    #   assert read_manifest(fixture_dir).content_hash == compute_content_hash(fixture_dir)
```

## Implementation Notes

- `psycopg` (v3) is already a dependency (used by integration tests and the
  langgraph store). Use it directly for COPY (`cursor.copy()` API).
- Keep subprocess use minimal and injectable: a module-level
  `run_pg_dump(args, env)` seam makes unit testing trivial.
- Pass credentials to pg_dump via the DSN argument; do not write .pgpass.
- The migrations tables are what let `async_store_context` (which always
  calls `store.setup()`) treat a restored per-run store as already migrated —
  verify against the installed `langgraph-checkpoint-postgres` version by
  running `store.setup()` locally and listing the tables it creates.
