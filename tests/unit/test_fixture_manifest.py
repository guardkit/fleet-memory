import json
import shutil
from pathlib import Path

import pytest

from fleet_memory.fixture import (
    FixtureManifest,
    compute_content_hash,
    read_manifest,
    write_manifest,
    UnknownFixtureError,
)

# Helper to create a temporary fixture directory with payload files
def create_fixture(tmp_path: Path, fixture_id: str, files: dict[str, bytes]) -> Path:
    fixture_root = tmp_path / "eval" / "fixtures" / fixture_id
    fixture_root.mkdir(parents=True)
    for rel, data in files.items():
        (fixture_root / rel).write_bytes(data)
    return fixture_root

def test_compute_content_hash_deterministic(tmp_path: Path):
    fixture_id = "demo"
    payload = {"a.txt": b"hello", "sub/b.txt": b"world"}
    fixture_dir = create_fixture(tmp_path, fixture_id, payload)
    # First hash
    h1 = compute_content_hash(fixture_dir)
    # Re‑order creation (different mtimes) – create new files with same content
    shutil.rmtree(fixture_dir)
    fixture_dir = create_fixture(tmp_path, fixture_id, payload)
    h2 = compute_content_hash(fixture_dir)
    assert h1 == h2

def test_compute_content_hash_sensitivity(tmp_path: Path):
    fixture_id = "sensitive"
    payload1 = {"a.txt": b"data"}
    payload2 = {"a.txt": b"data2"}
    dir1 = create_fixture(tmp_path, fixture_id, payload1)
    dir2 = create_fixture(tmp_path, f"{fixture_id}_2", payload2)
    assert compute_content_hash(dir1) != compute_content_hash(dir2)
    # Change filename only
    dir3 = create_fixture(tmp_path, f"{fixture_id}_3", {"b.txt": b"data"})
    assert compute_content_hash(dir1) != compute_content_hash(dir3)

def test_manifest_round_trip(tmp_path: Path):
    fixture_id = "manifest"
    payload = {"data.bin": b"\x00\x01"}
    fixture_dir = create_fixture(tmp_path, fixture_id, payload)
    manifest = FixtureManifest(
        fixture_id=fixture_id,
        created_at="2026-07-03T12:00:00Z",
        source_target="localhost:5432/db",
        content_hash=compute_content_hash(fixture_dir),
        table_row_counts={"tbl": 1},
        null_occurred_at_count=0,
        pg_dump_version="15",
    )
    write_manifest(manifest, fixture_dir)
    loaded = read_manifest(fixture_dir)
    assert loaded == manifest

def test_read_manifest_missing_raises(tmp_path: Path):
    fixture_id = "missing"
    fixture_dir = tmp_path / "eval" / "fixtures" / fixture_id
    fixture_dir.mkdir(parents=True)
    with pytest.raises(UnknownFixtureError) as exc:
        read_manifest(fixture_dir)
    assert fixture_id in str(exc.value)

def test_invalid_fixture_id(tmp_path: Path):
    # Empty ID should raise ValueError from fixture_dir helper
    with pytest.raises(ValueError):
        from fleet_memory.fixture import fixture_dir
        fixture_dir(fixture_id="")
    # Invalid characters
    with pytest.raises(ValueError):
        fixture_dir(fixture_id="bad/../id")
