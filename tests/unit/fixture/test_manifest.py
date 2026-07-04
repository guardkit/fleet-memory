# tests/unit/fixture/test_manifest.py
"""Unit tests for the fixture package implementation."""

from pathlib import Path
import json
import pytest

import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(root / "src"))
from fleet_memory.fixture import (
    FixtureManifest,
    compute_content_hash,
    write_manifest,
    read_manifest,
    UnknownFixtureError,
)


def create_payload(dir_path: Path, files: dict[str, str]):
    """Helper to create payload files with given content."""
    for rel, content in files.items():
        file_path = dir_path / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def test_compute_content_hash_deterministic(tmp_path: Path):
    fixture_dir = tmp_path / "myfixture"
    fixture_dir.mkdir()
    # create two payload files
    create_payload(fixture_dir, {"a.txt": "hello", "sub/b.txt": "world"})
    hash1 = compute_content_hash(fixture_dir)
    # modify mtimes
    (fixture_dir / "a.txt").touch()
    (fixture_dir / "sub/b.txt").touch()
    hash2 = compute_content_hash(fixture_dir)
    assert hash1 == hash2


def test_compute_content_hash_sensitivity(tmp_path: Path):
    fixture_dir = tmp_path / "sensitive"
    fixture_dir.mkdir()
    create_payload(fixture_dir, {"a.txt": "data"})
    base_hash = compute_content_hash(fixture_dir)
    # change content
    (fixture_dir / "a.txt").write_text("different", encoding="utf-8")
    changed_hash = compute_content_hash(fixture_dir)
    assert base_hash != changed_hash
    # add new file
    (fixture_dir / "b.txt").write_text("extra", encoding="utf-8")
    added_hash = compute_content_hash(fixture_dir)
    assert added_hash != base_hash


def test_manifest_round_trip(tmp_path: Path):
    fixture_dir = tmp_path / "manifest_test"
    fixture_dir.mkdir()
    # create payload
    create_payload(fixture_dir, {"data.txt": "payload"})
    content_hash = compute_content_hash(fixture_dir)
    manifest = FixtureManifest(
        fixture_id="testid",
        created_at="2026-07-03T00:00:00Z",
        source_target="localhost:5432/db",
        content_hash=content_hash,
        table_row_counts={"tbl": 1},
        null_occurred_at_count=0,
        pg_dump_version="15",
    )
    write_manifest(manifest, fixture_dir)
    loaded = read_manifest(fixture_dir)
    assert loaded == manifest


def test_missing_fixture_raises(tmp_path: Path):
    missing_dir = tmp_path / "nope"
    with pytest.raises(UnknownFixtureError) as exc:
        read_manifest(missing_dir)
    assert "nope" in str(exc.value)


def test_invalid_fixture_id(tmp_path: Path):
    from fleet_memory.fixture import fixture_dir
    with pytest.raises(ValueError):
        fixture_dir("Invalid/ID", tmp_path)
