"""Hash-verified fixture restore into a fresh per-run Postgres (TASK-ABL5-002).

``restore_fixture`` verifies the fixture's content hash *before* touching the
target database (a corrupted fixture must never grade a rollout), refuses a
target that already contains any of the fixture's tables (per-run stores are
fresh by contract; a silent merge would corrupt the corpus), then applies
schema.sql and COPYs each data file in schema-dependency order — ``store``
before ``store_vectors`` (FK) — inside a single transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fleet_memory.fixture import (
    FixtureError,
    FixtureHashMismatchError,
    FixtureManifest,
    compute_content_hash,
    fixture_dir,
    read_manifest,
)
from fleet_memory.fixture.dsn import sanitize_target, scrub_secrets
from fleet_memory.fixture.snapshot import _default_connect, _quote_ident

__all__ = ["RESTORE_ORDER", "build_copy_in_sql", "restore_fixture"]

# Schema-dependency order: migration-version tables first (so store.setup()
# on the restored database is a no-op), then store before store_vectors (FK).
RESTORE_ORDER: tuple[str, ...] = ("store_migrations", "vector_migrations", "store", "store_vectors")

EXISTING_TABLES_SQL = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name = ANY(%s) "
    "ORDER BY table_name"
)


def build_copy_in_sql(table: str) -> str:
    # Schema-qualified: schema.sql (pg_dump output) empties search_path.
    return f'COPY "public".{_quote_ident(table)} FROM STDIN'


def _verified_tables(fdir: Path, fixture_id: str) -> list[str]:
    """Hash-verify the fixture and return its tables in restore order."""
    manifest = read_manifest(fdir)
    actual_hash = compute_content_hash(fdir)
    if actual_hash != manifest.content_hash:
        raise FixtureHashMismatchError(fixture_id, manifest.content_hash, actual_hash)

    data_dir = fdir / "data"
    tables = sorted(path.stem for path in data_dir.glob("*.copy")) if data_dir.is_dir() else []
    if not tables:
        raise FixtureError(f"Fixture '{fixture_id}' contains no data files")
    unknown = sorted(set(tables) - set(RESTORE_ORDER))
    if unknown:
        raise FixtureError(
            f"Fixture '{fixture_id}' contains data for unknown tables: {', '.join(unknown)}"
        )
    return [table for table in RESTORE_ORDER if table in tables]


def restore_fixture(
    fixture_id: str,
    target_dsn: str,
    fixtures_root: Path | str,
    *,
    connection_factory: Callable[[str], Any] | None = None,
) -> FixtureManifest:
    """Restore ``fixture_id`` into the (fresh) database at ``target_dsn``.

    Returns the fixture's manifest so callers can log fixture id + content
    hash per rollout.
    """
    fdir = fixture_dir(fixture_id, fixtures_root)
    tables = _verified_tables(fdir, fixture_id)
    manifest = read_manifest(fdir)
    schema_sql = (fdir / "schema.sql").read_text(encoding="utf-8")

    target = sanitize_target(target_dsn)
    connect = connection_factory or _default_connect
    try:
        conn = connect(target_dsn)
    except Exception as exc:
        detail = scrub_secrets(str(exc), target_dsn)
        raise FixtureError(f"Cannot connect to {target}: {detail}") from None

    try:
        cur = conn.cursor()
        cur.execute(EXISTING_TABLES_SQL, (list(tables),))
        existing = sorted(row[0] for row in cur.fetchall())
        if existing:
            raise FixtureError(
                f"Target database {target} already contains fixture tables: "
                f"{', '.join(existing)}; per-run stores must be fresh"
            )

        try:
            cur.execute(schema_sql)
            for table in tables:
                data = (fdir / "data" / f"{table}.copy").read_bytes()
                with cur.copy(build_copy_in_sql(table)) as copy:
                    copy.write(data)
            conn.commit()
        except FixtureError:
            raise
        except Exception as exc:
            detail = scrub_secrets(str(exc), target_dsn)
            raise FixtureError(
                f"Restore of fixture '{fixture_id}' into {target} failed: {detail}"
            ) from None
    finally:
        conn.close()

    return manifest
