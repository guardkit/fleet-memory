"""Deterministic pg_dump-based snapshot of a fleet-memory store (TASK-ABL5-002).

``create_snapshot`` dumps a store into a versioned fixture directory:

    <fixtures_root>/<fixture_id>/
    ├── manifest.json     # FixtureManifest (TASK-ABL5-001 contract)
    ├── schema.sql        # pg_dump --schema-only, volatile version comments stripped
    └── data/<table>.copy # COPY TEXT format, one file per table, PK-ordered rows

The acceptance bar is byte-identity: restoring a fixture into a fresh database
and re-snapshotting it must reproduce byte-identical payload files. Hence:

- rows are exported with ``COPY (SELECT * FROM <t> ORDER BY <pk cols>) TO STDOUT``
  so physical row order never leaks into the dump;
- the data session runs read-only (``default_transaction_read_only = on`` — the
  P3 "never write to the live store" guarantee is structural) in UTC;
- the two volatile ``-- Dumped …`` comment lines are stripped from schema.sql
  and recorded in manifest metadata instead.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fleet_memory.fixture import (
    FixtureError,
    FixtureManifest,
    compute_content_hash,
    fixture_dir,
    write_manifest,
)
from fleet_memory.fixture.dsn import sanitize_target, scrub_secrets

__all__ = [
    "EXPECTED_TABLES",
    "build_copy_out_sql",
    "build_pg_dump_args",
    "create_snapshot",
    "run_pg_dump",
    "strip_volatile_comments",
]

# The langgraph AsyncPostgresStore table set (verified against the installed
# langgraph-checkpoint-postgres: store.setup() creates the two data tables and
# the two migration-version tables). Migrations tables are included so that
# store.setup() against a restored database is a no-op, not a re-migration.
EXPECTED_TABLES = frozenset({"store", "store_vectors", "store_migrations", "vector_migrations"})

# Session setup for the data export: read-only makes the "never write to the
# live store" guarantee structural; UTC pins timestamptz text rendering.
READ_ONLY_SESSION_SQL: tuple[str, ...] = (
    "SET default_transaction_read_only = on",
    "SET TIME ZONE 'UTC'",
)

TABLE_DISCOVERY_SQL = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
    "ORDER BY table_name"
)

PRIMARY_KEY_SQL = (
    "SELECT a.attname "
    "FROM pg_index i "
    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey) "
    "WHERE i.indrelid = %s::regclass AND i.indisprimary "
    "ORDER BY array_position(i.indkey::int2[], a.attnum)"
)

# Covers both JSON null and absent key; temporal logic runs on
# episode_meta.occurred_at, never row created_at.
NULL_OCCURRED_AT_SQL = (
    "SELECT count(*) FROM public.store "
    "WHERE (value #>> '{episode_meta,occurred_at}') IS NULL"
)

_VOLATILE_PREFIXES = {
    "-- Dumped from database version": "server_version",
    "-- Dumped by pg_dump version": "pg_dump_version",
}

# pg_dump >= 16.10 (CVE-2025-8714 hardening) wraps dumps in psql-only
# \restrict <random-token> / \unrestrict meta-commands. The token is random
# per dump session (breaks byte-stability) and the lines are not SQL (breaks
# psycopg-based restore); dropping them is safe because we never replay the
# dump through psql — schema.sql is executed via psycopg, which does not
# interpret meta-commands.
_PSQL_META_PREFIXES = ("\\restrict ", "\\unrestrict ")


def run_pg_dump(
    args: list[str], env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run pg_dump as an argument list (never a shell string). Injectable seam."""
    return subprocess.run(args, env=env, capture_output=True, text=True, check=False)


def build_pg_dump_args(source_dsn: str) -> list[str]:
    """pg_dump argv for the schema dump; the DSN is a discrete argv element."""
    return [
        "pg_dump",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        source_dsn,
    ]


def strip_volatile_comments(schema_sql: str) -> tuple[str, dict[str, str]]:
    """Remove volatile dump lines; return (stable text, versions).

    Drops the two ``-- Dumped …`` comment lines (version strings move into
    manifest metadata) and the random-token ``\\restrict``/``\\unrestrict``
    psql meta-command lines, keeping schema.sql byte-stable across dump
    sessions against equivalent databases.
    """
    kept: list[str] = []
    versions: dict[str, str] = {}
    for line in schema_sql.splitlines():
        if line.startswith(_PSQL_META_PREFIXES):
            continue
        for prefix, key in _VOLATILE_PREFIXES.items():
            if line.startswith(prefix):
                versions[key] = line.removeprefix(prefix).strip()
                break
        else:
            kept.append(line)
    text = "\n".join(kept)
    if text and not text.endswith("\n"):
        text += "\n"
    return text, versions


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def build_copy_out_sql(table: str, pk_columns: list[str]) -> str:
    """COPY-out statement with explicit primary-key ordering (determinism)."""
    if not pk_columns:
        raise FixtureError(
            f"Table '{table}' has no primary key; cannot produce a deterministic dump"
        )
    order = ", ".join(_quote_ident(col) for col in pk_columns)
    return f'COPY (SELECT * FROM "public".{_quote_ident(table)} ORDER BY {order}) TO STDOUT'


def _default_connect(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn)


def _dump_schema(
    source_dsn: str,
    target: str,
    runner: Callable[[list[str], Mapping[str, str] | None], subprocess.CompletedProcess[str]],
) -> tuple[str, dict[str, str]]:
    result = runner(build_pg_dump_args(source_dsn), None)
    if result.returncode != 0:
        detail = scrub_secrets(result.stderr or "", source_dsn).strip()
        raise FixtureError(
            f"pg_dump failed for {target} (exit {result.returncode}): {detail}"
        )
    return strip_volatile_comments(result.stdout)


def _export_data(
    cur: Any, target: str, data_dir: Path
) -> tuple[dict[str, int], int]:
    """Export every store table PK-ordered; return (row counts, null count)."""
    for statement in READ_ONLY_SESSION_SQL:
        cur.execute(statement)

    cur.execute(TABLE_DISCOVERY_SQL)
    tables = sorted(row[0] for row in cur.fetchall())
    unexpected = sorted(set(tables) - EXPECTED_TABLES)
    if unexpected:
        raise FixtureError(
            f"Unexpected tables in source database {target}: {', '.join(unexpected)}; "
            "refusing to snapshot (nothing may be silently dropped)"
        )
    if "store" not in tables:
        raise FixtureError(
            f"Source database {target} has no 'store' table; not a fleet-memory store"
        )

    data_dir.mkdir(parents=True)
    row_counts: dict[str, int] = {}
    for table in tables:
        cur.execute(PRIMARY_KEY_SQL, (f"public.{table}",))
        pk_columns = [row[0] for row in cur.fetchall()]
        copy_sql = build_copy_out_sql(table, pk_columns)
        with (data_dir / f"{table}.copy").open("wb") as out, cur.copy(copy_sql) as copy:
            for chunk in copy:
                out.write(bytes(chunk))
        cur.execute(f'SELECT count(*) FROM "public".{_quote_ident(table)}')
        row_counts[table] = int(cur.fetchone()[0])

    cur.execute(NULL_OCCURRED_AT_SQL)
    null_occurred_at_count = int(cur.fetchone()[0])
    return row_counts, null_occurred_at_count


def create_snapshot(
    source_dsn: str,
    fixture_id: str,
    fixtures_root: Path | str,
    *,
    connection_factory: Callable[[str], Any] | None = None,
    pg_dump_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> FixtureManifest:
    """Snapshot the store at ``source_dsn`` into ``<fixtures_root>/<fixture_id>/``.

    Refuses to overwrite an existing fixture id — versioned fixtures are
    immutable; a new corpus is a new id. On any failure the partially written
    fixture directory is removed.
    """
    target = sanitize_target(source_dsn)
    fdir = fixture_dir(fixture_id, fixtures_root)
    if fdir.exists():
        raise FixtureError(
            f"Fixture '{fixture_id}' already exists at {fdir}; "
            "fixtures are immutable — use a new fixture id"
        )

    runner = pg_dump_runner or run_pg_dump
    connect = connection_factory or _default_connect

    schema_sql, versions = _dump_schema(source_dsn, target, runner)

    fdir.mkdir(parents=True)
    try:
        (fdir / "schema.sql").write_text(schema_sql, encoding="utf-8")

        try:
            conn = connect(source_dsn)
        except Exception as exc:
            detail = scrub_secrets(str(exc), source_dsn)
            raise FixtureError(f"Cannot connect to {target}: {detail}") from None
        try:
            cur = conn.cursor()
            try:
                row_counts, null_count = _export_data(cur, target, fdir / "data")
            except FixtureError:
                raise
            except Exception as exc:
                detail = scrub_secrets(str(exc), source_dsn)
                raise FixtureError(f"Snapshot of {target} failed: {detail}") from None
        finally:
            conn.close()

        manifest = FixtureManifest(
            fixture_id=fixture_id,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source_target=target,
            content_hash=compute_content_hash(fdir),
            table_row_counts=row_counts,
            null_occurred_at_count=null_count,
            pg_dump_version=_format_versions(versions),
        )
        write_manifest(manifest, fdir)
        return manifest
    except BaseException:
        shutil.rmtree(fdir, ignore_errors=True)
        raise


def _format_versions(versions: dict[str, str]) -> str:
    pg_dump_version = versions.get("pg_dump_version", "")
    server_version = versions.get("server_version", "")
    if pg_dump_version and server_version:
        return f"{pg_dump_version} (server {server_version})"
    return pg_dump_version or server_version
