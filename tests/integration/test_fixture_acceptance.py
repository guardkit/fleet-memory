"""Seeded-store acceptance tests for the ablation fixture tooling (TASK-ABL5-006).

The feature's acceptance proof as executable tests, run against seeded local
copies on the ephemeral Docker Postgres only — never the live store:

1. Round-trip byte-identity: seed -> snapshot -> restore -> re-snapshot gives
   byte-identical payload files and an equal content hash.
2. FEAT-HARV cut proof: a 2026-06-25 cut excludes the seeded OUT-SMOKE
   build_outcome (occurred_at 2026-06-29) and every NULL-occurred_at entry
   (count == manifest.null_occurred_at_count), keeps pre-cut entries, and is
   idempotent with no orphaned vectors.
3. Restore refusals: unknown fixture id, tampered payload byte, non-empty
   target.
4. Scratch isolation: rollout writes under scratch_namespace are invisible to
   the corpus project and fully removed by discard_scratch; siblings survive.
5. Source read-only: create_snapshot never mutates the source rows.

Run explicitly (requires Docker; deselected from the default suite):

    .guardkit/venv/bin/python -m pytest \
        tests/integration/test_fixture_acceptance.py -m integration -v
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import psycopg
import pytest

from fleet_memory.embed import make_fake_embed
from fleet_memory.fixture import (
    FixtureError,
    FixtureHashMismatchError,
    FixtureManifest,
    UnknownFixtureError,
    fixture_dir,
)
from fleet_memory.fixture.restore import restore_fixture
from fleet_memory.fixture.scratch import (
    discard_scratch,
    list_scratch_projects,
    scratch_namespace,
)
from fleet_memory.fixture.snapshot import create_snapshot
from fleet_memory.fixture.temporal_cut import CutResult, apply_temporal_cut
from fleet_memory.settings import Settings
from fleet_memory.store import async_store_context

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.integration

# The acceptance anchors named by the task spec.
FIXTURE_ID = "v1t"
PROJECT = "guardkit"
CUT_DATE = date(2026, 6, 25)
OUT_SMOKE_NATURAL_KEY = f"build_outcome:{PROJECT}:OUT-SMOKE"
BOUNDARY_NATURAL_KEY = f"build_outcome:{PROJECT}:OUT-BOUNDARY"
HARV_NATURAL_KEY = f"chunk:{PROJECT}:FEAT-HARV-CHUNK-1"
OLD_WORK_NATURAL_KEY = f"decision:{PROJECT}:OLD-WORK-1"
NULL_SEED_COUNT = 5
CORPUS_ROW_COUNT = 4 + NULL_SEED_COUNT

_ABSENT = object()  # sentinel: entry has no episode_meta key at all

ORPHAN_VECTORS_SQL = (
    "SELECT count(*) FROM store_vectors sv "
    "LEFT JOIN store s USING (prefix, key) WHERE s.key IS NULL"
)


def _writer_shaped_value(
    payload_type: str,
    identifier: str,
    project: str,
    episode_meta: dict[str, Any] | None | object = _ABSENT,
) -> dict[str, Any]:
    """Value shaped like the deterministic writer's output (writer/core.py:187-205)."""
    payload_dict = {
        "identifier": identifier,
        "payload_type": payload_type,
        "project": project,
        "summary": f"Seeded acceptance entry {identifier}",
    }
    content_json = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
    value: dict[str, Any] = {
        "content": content_json,
        "content_hash": hashlib.sha256(content_json.encode("utf-8")).hexdigest(),
        "version": 1,
        "payload_type": payload_type,
        "natural_key": f"{payload_type}:{project}:{identifier}",
        "project": project,
        "identifier": identifier,
    }
    if episode_meta is not _ABSENT:
        meta = episode_meta if isinstance(episode_meta, dict) else {}
        value["episode_type"] = meta.get("episode_type")
        value["episode_meta"] = episode_meta
    return value


def _seed_entries() -> list[tuple[tuple[str, str, str], str, dict[str, Any]]]:
    """(namespace, key, value) triples mirroring the live-store shape (scope §2)."""

    def dated(episode_type: str, occurred_at: str) -> dict[str, Any]:
        return {"episode_type": episode_type, "occurred_at": occurred_at}

    entries: list[tuple[tuple[str, str, str], str, dict[str, Any]]] = [
        # The known post-FEAT entry the acceptance names.
        (
            ("fleet_memory", PROJECT, "build_outcome"),
            "seed_out_smoke",
            _writer_shaped_value(
                "build_outcome",
                "OUT-SMOKE",
                PROJECT,
                dated("build_outcome", "2026-06-29T00:00:00+00:00"),
            ),
        ),
        # FEAT-HARV-era chunk: must survive the cut.
        (
            ("fleet_memory", PROJECT, "chunk"),
            "seed_harv_chunk",
            _writer_shaped_value(
                "chunk",
                "FEAT-HARV-CHUNK-1",
                PROJECT,
                dated("chunk", "2026-06-24T12:00:00+00:00"),
            ),
        ),
        # Boundary entry: excluded by >= semantics.
        (
            ("fleet_memory", PROJECT, "build_outcome"),
            "seed_boundary",
            _writer_shaped_value(
                "build_outcome",
                "OUT-BOUNDARY",
                PROJECT,
                dated("build_outcome", "2026-06-25T00:00:00+00:00"),
            ),
        ),
        # Old-work entry: survives; its row created_at is "now" (backfill-era),
        # proving created_at is not the temporal axis.
        (
            ("fleet_memory", PROJECT, "decision"),
            "seed_old_work",
            _writer_shaped_value(
                "decision",
                "OLD-WORK-1",
                PROJECT,
                dated("decision", "2026-05-01T09:00:00+00:00"),
            ),
        ),
    ]

    # NULL_SEED_COUNT entries with NULL/absent occurred_at, mixing all three
    # live-store shapes: explicit None, episode_meta without the key, and no
    # episode_meta at all. All must be excluded by any cut.
    null_metas: list[dict[str, Any] | None | object] = [
        {"episode_type": "note", "occurred_at": None},
        {"episode_type": "note", "occurred_at": None},
        {"episode_type": "note"},
        {"episode_type": "note"},
        _ABSENT,
    ]
    assert len(null_metas) == NULL_SEED_COUNT
    for i, meta in enumerate(null_metas):
        entries.append(
            (
                ("fleet_memory", PROJECT, "note"),
                f"seed_null_{i}",
                _writer_shaped_value("note", f"NULL-{i}", PROJECT, meta),
            )
        )
    return entries


def _settings(dsn: str) -> Settings:
    """Settings for a seeded local copy; embed_url is never contacted (fake embed)."""
    return Settings(
        pg_dsn=dsn,
        embed_url="http://embed.invalid:9",
        embed_dims=768,
        pg_pool_min=1,
        pg_pool_max=4,
        pg_connect_timeout_s=10.0,
    )


async def _seed_corpus(dsn: str) -> None:
    """Seed the store copy the same way production data got there: store.aput."""
    fake_embed = make_fake_embed(dims=768)
    async with async_store_context(_settings(dsn), embed_fn=fake_embed) as store:
        for namespace, key, value in _seed_entries():
            await store.aput(namespace, key, value)


def _natural_keys(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as conn:
        rows = conn.execute("SELECT value->>'natural_key' FROM store").fetchall()
    return {row[0] for row in rows}


def _scalar(dsn: str, sql: str) -> Any:
    with psycopg.connect(dsn) as conn:
        return conn.execute(sql).fetchone()[0]


def _payload_files(fdir: Path) -> list[Path]:
    """Relative paths of every payload file (everything the content hash covers)."""
    return sorted(
        p.relative_to(fdir) for p in fdir.rglob("*") if p.is_file() and p.name != "manifest.json"
    )


@pytest.fixture(scope="session")
def fixtures_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("fixtures")


@pytest.fixture(scope="session")
def db_factory(ephemeral_pg: str) -> Callable[[str], str]:
    """Fresh databases per test via CREATE DATABASE on the one ephemeral instance."""

    def _create(label: str) -> str:
        name = f"abl5_{label}_{uuid4().hex[:8]}"
        with psycopg.connect(ephemeral_pg, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        return ephemeral_pg.rsplit("/", 1)[0] + f"/{name}"

    return _create


@pytest.fixture(scope="session")
def seeded_snapshot(
    db_factory: Callable[[str], str], fixtures_root: Path
) -> tuple[FixtureManifest, str]:
    """Seed a source store copy and snapshot it once as fixture ``v1t``.

    Yields (manifest, source_dsn). The seeding runs through the real
    AsyncPostgresStore with fake embeddings — exactly how production data got
    into the live store, minus the network.
    """
    source_dsn = db_factory("source")
    asyncio.run(_seed_corpus(source_dsn))
    manifest = create_snapshot(source_dsn, FIXTURE_ID, fixtures_root)
    return manifest, source_dsn


def test_seed_matches_declared_shape(seeded_snapshot: tuple[FixtureManifest, str]) -> None:
    """The seed itself honours the spec: 9 rows, NULL count == manifest count."""
    manifest, source_dsn = seeded_snapshot
    assert manifest.fixture_id == FIXTURE_ID
    assert manifest.table_row_counts["store"] == CORPUS_ROW_COUNT
    assert manifest.table_row_counts["store_vectors"] == CORPUS_ROW_COUNT
    assert manifest.null_occurred_at_count == NULL_SEED_COUNT
    assert OUT_SMOKE_NATURAL_KEY in _natural_keys(source_dsn)


def test_round_trip_byte_identity(
    seeded_snapshot: tuple[FixtureManifest, str],
    db_factory: Callable[[str], str],
    fixtures_root: Path,
) -> None:
    """Same fixture id => byte-identical retrieval corpus (hash stability)."""
    manifest, _ = seeded_snapshot
    target_dsn = db_factory("roundtrip")

    restored = restore_fixture(FIXTURE_ID, target_dsn, fixtures_root)
    assert restored.content_hash == manifest.content_hash

    rt_manifest = create_snapshot(target_dsn, "v1t_rt", fixtures_root)
    assert rt_manifest.content_hash == manifest.content_hash
    assert rt_manifest.table_row_counts == manifest.table_row_counts
    assert rt_manifest.null_occurred_at_count == manifest.null_occurred_at_count

    dir_a = fixture_dir(FIXTURE_ID, fixtures_root)
    dir_b = fixture_dir("v1t_rt", fixtures_root)
    rel_paths = _payload_files(dir_a)
    assert rel_paths == _payload_files(dir_b)
    assert Path("schema.sql") in rel_paths
    assert Path("data/store.copy") in rel_paths
    for rel in rel_paths:
        assert (dir_a / rel).read_bytes() == (dir_b / rel).read_bytes(), (
            f"payload file {rel} is not byte-identical after restore -> re-snapshot"
        )


def test_feat_harv_cut(
    seeded_snapshot: tuple[FixtureManifest, str],
    db_factory: Callable[[str], str],
    fixtures_root: Path,
) -> None:
    """The 2026-06-25 (FEAT-HARV) cut excludes OUT-SMOKE and all NULL entries."""
    manifest, _ = seeded_snapshot
    target_dsn = db_factory("cut")
    restore_fixture(FIXTURE_ID, target_dsn, fixtures_root)

    result = apply_temporal_cut(target_dsn, CUT_DATE)

    # OUT-SMOKE (2026-06-29) and the boundary entry (2026-06-25T00:00:00Z,
    # >= semantics) are excluded; pre-cut entries survive.
    remaining_keys = _natural_keys(target_dsn)
    assert OUT_SMOKE_NATURAL_KEY not in remaining_keys
    assert BOUNDARY_NATURAL_KEY not in remaining_keys
    assert HARV_NATURAL_KEY in remaining_keys
    assert OLD_WORK_NATURAL_KEY in remaining_keys
    assert result.excluded_after_cut == 2

    # Every NULL-occurred_at entry is excluded and the count matches the manifest.
    assert result.excluded_null == manifest.null_occurred_at_count == NULL_SEED_COUNT
    null_left = _scalar(
        target_dsn,
        "SELECT count(*) FROM store WHERE (value #>> '{episode_meta,occurred_at}') IS NULL",
    )
    assert null_left == 0

    assert result.remaining == 2 == len(remaining_keys)

    # No orphaned store_vectors rows.
    assert _scalar(target_dsn, ORPHAN_VECTORS_SQL) == 0
    assert _scalar(target_dsn, "SELECT count(*) FROM store_vectors") == 2

    # Idempotent: re-applying the same cut is a counted no-op.
    assert apply_temporal_cut(target_dsn, CUT_DATE) == CutResult(0, 0, 2)
    assert _natural_keys(target_dsn) == remaining_keys


def test_restore_refusals(
    seeded_snapshot: tuple[FixtureManifest, str],
    db_factory: Callable[[str], str],
    fixtures_root: Path,
    tmp_path: Path,
) -> None:
    """Unknown id, tampered payload byte, and non-empty target are all refused."""
    _, _ = seeded_snapshot
    target_dsn = db_factory("refusals")

    with pytest.raises(UnknownFixtureError):
        restore_fixture("no_such_fixture", target_dsn, fixtures_root)

    # Tamper one byte of a payload file in a private copy of the fixture.
    tampered_root = tmp_path / "fixtures"
    shutil.copytree(fixture_dir(FIXTURE_ID, fixtures_root), tampered_root / FIXTURE_ID)
    payload = tampered_root / FIXTURE_ID / "data" / "store.copy"
    blob = bytearray(payload.read_bytes())
    blob[0] ^= 0x01
    payload.write_bytes(bytes(blob))
    with pytest.raises(FixtureHashMismatchError):
        restore_fixture(FIXTURE_ID, target_dsn, tampered_root)

    # Neither refusal touched the database: a clean restore still succeeds ...
    restore_fixture(FIXTURE_ID, target_dsn, fixtures_root)
    assert _scalar(target_dsn, "SELECT count(*) FROM store") == CORPUS_ROW_COUNT

    # ... and restoring onto the now non-empty database is refused.
    with pytest.raises(FixtureError, match="already contains"):
        restore_fixture(FIXTURE_ID, target_dsn, fixtures_root)
    assert _scalar(target_dsn, "SELECT count(*) FROM store") == CORPUS_ROW_COUNT


async def test_scratch_isolation(
    seeded_snapshot: tuple[FixtureManifest, str],
    db_factory: Callable[[str], str],
    fixtures_root: Path,
    fake_embed: Callable[[str], list[float]],
) -> None:
    """Rollout writes live only in their scratch project and discard fully removes them."""
    _, _ = seeded_snapshot
    target_dsn = db_factory("scratch")
    restore_fixture(FIXTURE_ID, target_dsn, fixtures_root)

    with psycopg.connect(target_dsn) as conn:
        corpus_rows = set(conn.execute("SELECT prefix, key FROM store").fetchall())
    assert len(corpus_rows) == CORPUS_ROW_COUNT

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        return [fake_embed(text) for text in texts]

    run_01_ns = scratch_namespace("run_01", "build_outcome")
    run_02_ns = scratch_namespace("run_02", "build_outcome")
    async with async_store_context(_settings(target_dsn), embed_fn=embed_texts) as store:
        await store.aput(
            run_01_ns, "rollout_a", _writer_shaped_value("build_outcome", "RUN01-A", "scratch")
        )
        await store.aput(
            run_01_ns, "rollout_b", _writer_shaped_value("build_outcome", "RUN01-B", "scratch")
        )
        await store.aput(
            run_02_ns, "rollout_a", _writer_shaped_value("build_outcome", "RUN02-A", "scratch")
        )

        # Retrieval-shaped listing for the corpus project never sees scratch rows.
        items = await store.asearch(("fleet_memory", PROJECT), limit=50)
        assert len(items) == CORPUS_ROW_COUNT
        assert all(item.namespace[1] == PROJECT for item in items)

    # Corpus row set is unchanged outside scratch.
    with psycopg.connect(target_dsn) as conn:
        non_scratch = set(
            conn.execute(
                "SELECT prefix, key FROM store "
                "WHERE prefix NOT LIKE 'fleet_memory.scratch\\_%' ESCAPE '\\'"
            ).fetchall()
        )
    assert non_scratch == corpus_rows
    assert list_scratch_projects(target_dsn) == ["scratch_run_01", "scratch_run_02"]

    # Discard removes run_01's rows and vectors; the sibling survives.
    assert discard_scratch(target_dsn, "run_01") == 2
    assert _scalar(target_dsn, ORPHAN_VECTORS_SQL) == 0
    assert list_scratch_projects(target_dsn) == ["scratch_run_02"]
    sibling = _scalar(
        target_dsn,
        "SELECT count(*) FROM store WHERE prefix LIKE 'fleet_memory.scratch\\_run\\_02%' "
        "ESCAPE '\\'",
    )
    assert sibling == 1

    # Second discard is a no-op; the fixture corpus is untouched throughout.
    assert discard_scratch(target_dsn, "run_01") == 0
    with psycopg.connect(target_dsn) as conn:
        final_non_scratch = set(
            conn.execute(
                "SELECT prefix, key FROM store "
                "WHERE prefix NOT LIKE 'fleet_memory.scratch\\_%' ESCAPE '\\'"
            ).fetchall()
        )
    assert final_non_scratch == corpus_rows


def test_source_snapshot_is_read_only(
    seeded_snapshot: tuple[FixtureManifest, str], fixtures_root: Path
) -> None:
    """create_snapshot never mutates the seeded source (count + max(updated_at) stable)."""
    _, source_dsn = seeded_snapshot

    def state() -> tuple[Any, ...]:
        with psycopg.connect(source_dsn) as conn:
            store_state = conn.execute("SELECT count(*), max(updated_at) FROM store").fetchone()
            vec_state = conn.execute(
                "SELECT count(*), max(updated_at) FROM store_vectors"
            ).fetchone()
        return (*store_state, *vec_state)

    before = state()
    manifest = create_snapshot(source_dsn, "v1t_ro", fixtures_root)
    assert manifest.table_row_counts["store"] == CORPUS_ROW_COUNT
    assert state() == before
