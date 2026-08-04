"""Unit tests for the corpus manifest loader and kind resolution.

The loader is fail-loud: a tolerated manifest defect becomes a silent
double-publish (overlapping ownership) or a silent drop (unknown owner).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fleet_memory.reindex.manifest import (
    CorpusManifest,
    ManifestValidationError,
    load_manifest,
)


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _base_manifest() -> dict:
    return {
        "schema_version": 1,
        "project": "guardkit",
        "entries": [
            {
                "kind": "adr",
                "episode_type": "adr",
                "directories": ["docs/adr"],
                "owner": "harvest",
                "content_format": "markdown",
            },
            {
                "kind": "build_outcome",
                "episode_type": "build_outcome",
                "directories": ["tasks/completed"],
                "owner": "reindex",
                "content_format": "markdown",
            },
        ],
    }


class TestLoadManifest:
    """Loader accepts the real contract and fails loud on defects."""

    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _base_manifest())
        manifest = load_manifest(path)
        assert isinstance(manifest, CorpusManifest)
        assert manifest.schema_version == 1
        assert manifest.project == "guardkit"
        assert manifest.reindex_roots() == ["tasks/completed"]

    def test_loads_the_real_guardkit_manifest_fixture(self) -> None:
        """The checked-in fixture is the REAL exporter output — it must load."""
        fixture = Path(__file__).resolve().parents[2] / "fixtures" / "corpus_manifest.json"
        manifest = load_manifest(fixture)
        assert manifest.project == "guardkit"
        assert manifest.reindex_roots() == ["tasks/completed"]
        # kind == episode_type invariant carried across the repo boundary
        for entry in manifest.entries:
            assert entry.kind == entry.episode_type

    def test_missing_schema_version_fails_loud(self, tmp_path: Path) -> None:
        manifest = _base_manifest()
        del manifest["schema_version"]
        path = _write_manifest(tmp_path, manifest)
        with pytest.raises(ManifestValidationError, match="schema_version"):
            load_manifest(path)

    def test_unknown_owner_fails_loud(self, tmp_path: Path) -> None:
        manifest = _base_manifest()
        manifest["entries"][1]["owner"] = "chunker"
        path = _write_manifest(tmp_path, manifest)
        with pytest.raises(ManifestValidationError, match="Unknown owner 'chunker'"):
            load_manifest(path)

    def test_directory_covered_twice_fails_loud(self, tmp_path: Path) -> None:
        manifest = _base_manifest()
        manifest["entries"][0]["directories"].append("tasks/completed")
        path = _write_manifest(tmp_path, manifest)
        with pytest.raises(ManifestValidationError, match="covered twice"):
            load_manifest(path)

    def test_reindex_root_nested_in_harvest_dir_fails_loud(self, tmp_path: Path) -> None:
        manifest = _base_manifest()
        manifest["entries"][1]["directories"] = ["docs/adr/completed"]
        path = _write_manifest(tmp_path, manifest)
        with pytest.raises(ManifestValidationError, match="nested inside harvest"):
            load_manifest(path)

    def test_malformed_json_fails_loud(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ManifestValidationError, match="not valid JSON"):
            load_manifest(path)


class TestResolveKind:
    """resolve_kind uses longest-prefix match, mirroring guardkit."""

    @pytest.fixture
    def manifest(self, tmp_path: Path) -> CorpusManifest:
        return load_manifest(_write_manifest(tmp_path, _base_manifest()))

    def test_reindex_path_resolves(self, manifest: CorpusManifest) -> None:
        assert manifest.resolve_kind(
            "tasks/completed/2026-07/TASK-XYZ.md"
        ) == ("build_outcome", "reindex")

    def test_harvest_path_resolves_with_owner(self, manifest: CorpusManifest) -> None:
        assert manifest.resolve_kind("docs/adr/0001-adopt.md") == ("adr", "harvest")

    def test_outside_all_roots_returns_none(self, manifest: CorpusManifest) -> None:
        assert manifest.resolve_kind("src/main.py") is None
        assert manifest.resolve_kind("README.md") is None
        # Prefix similarity is not containment
        assert manifest.resolve_kind("tasks/completed-archive/TASK-1.md") is None

    def test_longest_prefix_wins(self, tmp_path: Path) -> None:
        manifest_dict = _base_manifest()
        manifest_dict["entries"].append(
            {
                "kind": "document",
                "episode_type": "document",
                "directories": ["docs"],
                "owner": "harvest",
                "content_format": "markdown",
            }
        )
        manifest = load_manifest(_write_manifest(tmp_path, manifest_dict))
        # docs/adr is longer than docs, so the adr entry claims the path
        assert manifest.resolve_kind("docs/adr/0001.md") == ("adr", "harvest")
        assert manifest.resolve_kind("docs/guides/intro.md") == ("document", "harvest")

    def test_exact_directory_match(self, manifest: CorpusManifest) -> None:
        assert manifest.resolve_kind("tasks/completed") == ("build_outcome", "reindex")
