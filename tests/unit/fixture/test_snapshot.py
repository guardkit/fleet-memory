"""Unit tests for fleet_memory.fixture.snapshot (TASK-ABL5-002).

All tests run without Docker/Postgres: the pg_dump subprocess and the psycopg
connection are injected seams (tests/unit/fixture/fakes.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleet_memory.fixture import FixtureError, compute_content_hash, read_manifest
from fleet_memory.fixture.snapshot import (
    READ_ONLY_SESSION_SQL,
    build_copy_out_sql,
    build_pg_dump_args,
    create_snapshot,
    strip_volatile_comments,
)
from tests.unit.fixture.fakes import (
    FakeDatabase,
    RecordingPgDump,
    pg_dump_result,
    refusing_connection_factory,
)

PASSWORD = "S3cr3tPW"
DSN = f"postgresql://ablation:{PASSWORD}@dbhost:5433/fleet"

SCHEMA_STDOUT = (
    "--\n"
    "-- PostgreSQL database dump\n"
    "--\n"
    "\\restrict RaNd0mT0kenChangesEveryDump\n"
    "-- Dumped from database version 16.4\n"
    "-- Dumped by pg_dump version 16.9\n"
    "\n"
    "CREATE TABLE public.store (prefix text NOT NULL, key text NOT NULL);\n"
    "\\unrestrict RaNd0mT0kenChangesEveryDump\n"
)


def make_store_db(**overrides) -> FakeDatabase:
    params = dict(
        tables=["store", "store_migrations", "store_vectors", "vector_migrations"],
        pk_columns={
            "store": ["prefix", "key"],
            "store_vectors": ["prefix", "key", "field_name"],
            "store_migrations": ["v"],
            "vector_migrations": ["v"],
        },
        copy_data={
            "store": [b"ns/a\tk1\t{}\n", b"ns/a\tk2\t{}\n"],
            "store_vectors": [b"ns/a\tk1\ttext\t[0.1]\n"],
            "store_migrations": [b"0\n1\n"],
            "vector_migrations": [b"0\n"],
        },
        row_counts={
            "store": 2,
            "store_vectors": 1,
            "store_migrations": 2,
            "vector_migrations": 1,
        },
        null_occurred_at_count=176,
    )
    params.update(overrides)
    return FakeDatabase(**params)


def snapshot(tmp_path: Path, db: FakeDatabase, runner: RecordingPgDump | None = None):
    runner = runner or RecordingPgDump(pg_dump_result(stdout=SCHEMA_STDOUT))
    manifest = create_snapshot(
        DSN,
        "v1",
        tmp_path,
        connection_factory=db.connection_factory,
        pg_dump_runner=runner,
    )
    return manifest, runner


# ----- command / SQL construction -----


def test_build_pg_dump_args_is_argv_with_dsn_element():
    args = build_pg_dump_args(DSN)
    assert args[0] == "pg_dump"
    for flag in ("--schema-only", "--no-owner", "--no-privileges"):
        assert flag in args
    # DSN is a discrete argv element, never interpolated into a shell string
    assert DSN in args
    assert args[args.index("--dbname") + 1] == DSN


def test_strip_volatile_comments_moves_versions_to_metadata():
    stable, versions = strip_volatile_comments(SCHEMA_STDOUT)
    assert "Dumped from database version" not in stable
    assert "Dumped by pg_dump version" not in stable
    assert "CREATE TABLE public.store" in stable
    assert versions == {"server_version": "16.4", "pg_dump_version": "16.9"}


def test_strip_volatile_comments_drops_random_token_restrict_lines():
    # pg_dump >= 16.10 wraps dumps in \restrict/\unrestrict with a token that
    # is random per dump session; it must not reach schema.sql (byte-stability
    # and the psycopg-based restore both require plain SQL).
    stable, _ = strip_volatile_comments(SCHEMA_STDOUT)
    assert "\\restrict" not in stable
    assert "\\unrestrict" not in stable
    assert "RaNd0mT0ken" not in stable


def test_build_copy_out_sql_orders_by_primary_key():
    sql = build_copy_out_sql("store", ["prefix", "key"])
    assert sql == 'COPY (SELECT * FROM "public"."store" ORDER BY "prefix", "key") TO STDOUT'


def test_build_copy_out_sql_without_pk_raises():
    with pytest.raises(FixtureError, match="no primary key"):
        build_copy_out_sql("store", [])


# ----- create_snapshot happy path -----


def test_create_snapshot_writes_layout_and_verifiable_manifest(tmp_path: Path):
    db = make_store_db()
    manifest, _ = snapshot(tmp_path, db)
    fdir = tmp_path / "v1"

    assert (fdir / "schema.sql").is_file()
    assert (fdir / "manifest.json").is_file()
    for table, chunks in db.copy_data.items():
        assert (fdir / "data" / f"{table}.copy").read_bytes() == b"".join(chunks)

    assert "Dumped by pg_dump version" not in (fdir / "schema.sql").read_text()
    assert manifest.fixture_id == "v1"
    assert manifest.source_target == "dbhost:5433/fleet"
    assert manifest.table_row_counts == db.row_counts
    assert manifest.null_occurred_at_count == 176
    assert "16.9" in manifest.pg_dump_version
    assert manifest.content_hash == compute_content_hash(fdir)
    assert read_manifest(fdir) == manifest


def test_create_snapshot_session_is_read_only_utc(tmp_path: Path):
    db = make_store_db()
    snapshot(tmp_path, db)
    statements = [sql for sql, _ in db.executed]
    # session setup runs first, before any discovery or data read
    assert statements[0] == "SET default_transaction_read_only = on"
    assert statements[1] == "SET TIME ZONE 'UTC'"
    assert statements[:2] == list(READ_ONLY_SESSION_SQL)


def test_create_snapshot_copy_statements_are_pk_ordered(tmp_path: Path):
    db = make_store_db()
    snapshot(tmp_path, db)
    copy_sqls = [sql for sql, _ in db.executed if sql.startswith("COPY (")]
    assert (
        'COPY (SELECT * FROM "public"."store" ORDER BY "prefix", "key") TO STDOUT' in copy_sqls
    )
    assert (
        'COPY (SELECT * FROM "public"."store_vectors" '
        'ORDER BY "prefix", "key", "field_name") TO STDOUT' in copy_sqls
    )


def test_create_snapshot_invokes_pg_dump_via_argv(tmp_path: Path):
    db = make_store_db()
    _, runner = snapshot(tmp_path, db)
    assert len(runner.calls) == 1
    args, _env = runner.calls[0]
    assert isinstance(args, list)
    assert args == build_pg_dump_args(DSN)


# ----- refusal paths -----


def test_create_snapshot_refuses_existing_fixture_id(tmp_path: Path):
    (tmp_path / "v1").mkdir(parents=True)
    runner = RecordingPgDump(pg_dump_result(stdout=SCHEMA_STDOUT))
    with pytest.raises(FixtureError, match="already exists"):
        create_snapshot(
            DSN,
            "v1",
            tmp_path,
            connection_factory=refusing_connection_factory,
            pg_dump_runner=runner,
        )
    assert runner.calls == []  # refused before running pg_dump


def test_create_snapshot_fails_loudly_on_table_without_pk(tmp_path: Path):
    db = make_store_db()
    db.pk_columns.pop("store_migrations")
    with pytest.raises(FixtureError, match="store_migrations.*no primary key"):
        snapshot(tmp_path, db)
    assert not (tmp_path / "v1").exists()  # partial fixture cleaned up


def test_create_snapshot_fails_loudly_on_unexpected_table(tmp_path: Path):
    db = make_store_db()
    db.tables.append("evil_extra")
    with pytest.raises(FixtureError, match="evil_extra"):
        snapshot(tmp_path, db)
    assert not (tmp_path / "v1").exists()


def test_create_snapshot_requires_store_table(tmp_path: Path):
    db = make_store_db(tables=["store_migrations"], copy_data={}, row_counts={})
    with pytest.raises(FixtureError, match="no 'store' table"):
        snapshot(tmp_path, db)


# ----- credential hygiene -----


def test_pg_dump_failure_never_leaks_password(tmp_path: Path):
    runner = RecordingPgDump(
        pg_dump_result(stderr=f'pg_dump: error: connection to "{DSN}" failed', returncode=1)
    )
    with pytest.raises(FixtureError) as excinfo:
        create_snapshot(
            DSN,
            "v1",
            tmp_path,
            connection_factory=refusing_connection_factory,
            pg_dump_runner=runner,
        )
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "dbhost:5433/fleet" in message
    assert "exit 1" in message
    assert not (tmp_path / "v1").exists()


def test_connect_failure_never_leaks_password(tmp_path: Path):
    def failing_factory(dsn: str):
        raise RuntimeError(f"could not connect using {dsn} (password={PASSWORD})")

    runner = RecordingPgDump(pg_dump_result(stdout=SCHEMA_STDOUT))
    with pytest.raises(FixtureError) as excinfo:
        create_snapshot(
            DSN, "v1", tmp_path, connection_factory=failing_factory, pg_dump_runner=runner
        )
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "dbhost:5433/fleet" in message


# ----- seam test: TASK-ABL5-001 manifest contract -----


@pytest.mark.seam
def test_fixture_manifest_hash_contract(tmp_path):
    """Verify snapshot output hash-verifies via the TASK-ABL5-001 helpers.

    Contract: content_hash = SHA-256 over payload files (rel_path + NUL +
    bytes, sorted by relative path), manifest.json excluded.
    Producer: TASK-ABL5-001
    """
    from fleet_memory.fixture.manifest import compute_content_hash, read_manifest

    db = make_store_db()
    snapshot(tmp_path, db)
    fdir = tmp_path / "v1"
    assert read_manifest(fdir).content_hash == compute_content_hash(fdir)
