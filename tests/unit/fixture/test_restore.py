"""Unit tests for fleet_memory.fixture.restore (TASK-ABL5-002).

Fixtures are built on disk with the TASK-ABL5-001 helpers; the target-database
connection is an injected fake (tests/unit/fixture/fakes.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleet_memory.fixture import (
    FixtureError,
    FixtureHashMismatchError,
    FixtureManifest,
    UnknownFixtureError,
    compute_content_hash,
    write_manifest,
)
from fleet_memory.fixture.restore import build_copy_in_sql, restore_fixture
from tests.unit.fixture.fakes import FakeDatabase, refusing_connection_factory

PASSWORD = "S3cr3tPW"
DSN = f"postgresql://runner:{PASSWORD}@runhost:5544/perrun"

SCHEMA_SQL = "CREATE TABLE public.store (prefix text NOT NULL, key text NOT NULL);\n"

PAYLOADS = {
    "store": b"ns/a\tk1\t{}\nns/a\tk2\t{}\n",
    "store_vectors": b"ns/a\tk1\ttext\t[0.1]\n",
    "store_migrations": b"0\n1\n",
    "vector_migrations": b"0\n",
}


def build_fixture(
    fixtures_root: Path,
    fixture_id: str = "v1",
    payloads: dict[str, bytes] | None = None,
) -> Path:
    """Write a snapshot-shaped fixture with a valid manifest (ABL5-001 helpers)."""
    payloads = PAYLOADS if payloads is None else payloads
    fdir = fixtures_root / fixture_id
    (fdir / "data").mkdir(parents=True)
    (fdir / "schema.sql").write_text(SCHEMA_SQL, encoding="utf-8")
    for table, data in payloads.items():
        (fdir / "data" / f"{table}.copy").write_bytes(data)
    manifest = FixtureManifest(
        fixture_id=fixture_id,
        created_at="2026-07-04T00:00:00Z",
        source_target="dbhost:5433/fleet",
        content_hash=compute_content_hash(fdir),
        table_row_counts={table: 1 for table in payloads},
        null_occurred_at_count=176,
        pg_dump_version="16.9",
    )
    write_manifest(manifest, fdir)
    return fdir


# ----- refusal paths (all before touching the target database) -----


def test_unknown_fixture_raises_without_touching_target(tmp_path: Path):
    with pytest.raises(UnknownFixtureError):
        restore_fixture("missing", DSN, tmp_path, connection_factory=refusing_connection_factory)


def test_tampered_payload_raises_hash_mismatch_before_target(tmp_path: Path):
    fdir = build_fixture(tmp_path)
    copy_path = fdir / "data" / "store.copy"
    data = bytearray(copy_path.read_bytes())
    data[0] ^= 0xFF  # flip one byte
    copy_path.write_bytes(bytes(data))
    with pytest.raises(FixtureHashMismatchError):
        restore_fixture("v1", DSN, tmp_path, connection_factory=refusing_connection_factory)


def test_unknown_table_data_file_is_refused(tmp_path: Path):
    fdir = build_fixture(tmp_path, payloads={**PAYLOADS, "weird": b"x\n"})
    assert (fdir / "data" / "weird.copy").is_file()
    with pytest.raises(FixtureError, match="weird"):
        restore_fixture("v1", DSN, tmp_path, connection_factory=refusing_connection_factory)


def test_non_empty_target_is_refused(tmp_path: Path):
    build_fixture(tmp_path)
    db = FakeDatabase(existing_tables=["store", "store_migrations"])
    with pytest.raises(FixtureError, match="already contains") as excinfo:
        restore_fixture("v1", DSN, tmp_path, connection_factory=db.connection_factory)
    assert "store" in str(excinfo.value)
    # refusal happens before any schema/data statement reaches the target
    assert not any("CREATE" in sql for sql, _ in db.executed)
    assert not any(sql.startswith("COPY") for sql, _ in db.executed)
    assert db.copy_writes == []
    assert not db.committed
    assert db.closed


# ----- happy path -----


def test_restore_applies_schema_then_copies_in_dependency_order(tmp_path: Path):
    build_fixture(tmp_path)
    db = FakeDatabase()
    manifest = restore_fixture("v1", DSN, tmp_path, connection_factory=db.connection_factory)

    statements = [sql for sql, _ in db.executed]
    assert SCHEMA_SQL in statements
    copy_order = [sql for sql in statements if sql.startswith("COPY ")]
    assert copy_order == [
        'COPY "public"."store_migrations" FROM STDIN',
        'COPY "public"."vector_migrations" FROM STDIN',
        'COPY "public"."store" FROM STDIN',
        'COPY "public"."store_vectors" FROM STDIN',
    ]
    # store before store_vectors (FK), schema before any COPY
    assert statements.index(SCHEMA_SQL) < statements.index(copy_order[0])
    assert db.copy_writes == [
        ("store_migrations", PAYLOADS["store_migrations"]),
        ("vector_migrations", PAYLOADS["vector_migrations"]),
        ("store", PAYLOADS["store"]),
        ("store_vectors", PAYLOADS["store_vectors"]),
    ]
    assert db.committed
    assert db.closed
    assert manifest.fixture_id == "v1"
    assert manifest.content_hash == compute_content_hash(tmp_path / "v1")


def test_restore_handles_subset_of_tables(tmp_path: Path):
    payloads = {"store": PAYLOADS["store"], "store_migrations": PAYLOADS["store_migrations"]}
    build_fixture(tmp_path, payloads=payloads)
    db = FakeDatabase()
    restore_fixture("v1", DSN, tmp_path, connection_factory=db.connection_factory)
    copy_order = [sql for sql, _ in db.executed if sql.startswith("COPY ")]
    assert copy_order == [
        'COPY "public"."store_migrations" FROM STDIN',
        'COPY "public"."store" FROM STDIN',
    ]


def test_build_copy_in_sql_is_schema_qualified():
    assert build_copy_in_sql("store") == 'COPY "public"."store" FROM STDIN'


# ----- credential hygiene -----


def test_refusal_error_never_leaks_password(tmp_path: Path):
    build_fixture(tmp_path)
    db = FakeDatabase(existing_tables=["store"])
    with pytest.raises(FixtureError) as excinfo:
        restore_fixture("v1", DSN, tmp_path, connection_factory=db.connection_factory)
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "runhost:5544/perrun" in message


def test_connect_failure_never_leaks_password(tmp_path: Path):
    build_fixture(tmp_path)

    def failing_factory(dsn: str):
        raise RuntimeError(f"could not connect using {dsn} (password={PASSWORD})")

    with pytest.raises(FixtureError) as excinfo:
        restore_fixture("v1", DSN, tmp_path, connection_factory=failing_factory)
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "runhost:5544/perrun" in message
