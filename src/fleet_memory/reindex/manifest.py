"""Corpus manifest: the cross-repo ownership contract for reindexing.

The manifest is exported by guardkit (``python -m guardkit.memory.harvest_taxonomy
--json``) and declares which corpus directories each pipeline owns:
``owner=="harvest"`` directories are published by guardkit's prose harvester;
``owner=="reindex"`` directories are walked by THIS pipeline and parsed into typed
payloads. The reindex walker descends ONLY reindex-owned roots — this is the
structural fix for the 63,683-file worktree inflation (walking the whole checkout
swept .guardkit/worktrees and produced "70,903 processed, 0 published").

Security property: the loader fails loud on any manifest that could make a file
publishable by both pipelines (overlapping directories, a reindex root nested in a
harvest dir) or that carries an unknown owner. A silently-tolerated manifest defect
becomes a silent double-publish or a silent drop.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

# The only pipeline owners the contract recognizes
KNOWN_OWNERS = frozenset({"harvest", "reindex"})


class ManifestValidationError(ValueError):
    """Raised when a corpus manifest is structurally invalid (fail-loud)."""


class ManifestEntry(BaseModel):
    """One taxonomy entry from the guardkit corpus manifest.

    Attributes:
        kind: Manifest key (guardkit pins kind == episode_type)
        episode_type: NATS subject segment / typed payload category
        directories: Repo-relative directory roots this entry covers
        owner: Which pipeline publishes these directories ("harvest" | "reindex")
        content_format: Source content format (markdown for all current entries)
    """

    kind: str
    episode_type: str
    directories: list[str]
    owner: str
    content_format: str


class CorpusManifest(BaseModel):
    """Parsed corpus manifest with kind resolution by longest-prefix match.

    Attributes:
        schema_version: Manifest schema version (currently 1)
        project: Project the manifest describes (e.g. "guardkit")
        entries: Taxonomy entries covering the corpus directories
    """

    schema_version: int
    project: str
    entries: list[ManifestEntry]

    def reindex_roots(self) -> list[str]:
        """Return the repo-relative directories owned by the reindex pipeline."""
        roots: list[str] = []
        for entry in self.entries:
            if entry.owner == "reindex":
                roots.extend(entry.directories)
        return roots

    def resolve_kind(self, repo_relative_path: str) -> tuple[str, str] | None:
        """Resolve (kind, owner) for a repo-relative path via longest-prefix match.

        Mirrors guardkit's episode_type_for so both repos agree on which entry
        claims a path. Returns None for paths outside every manifest directory.

        Args:
            repo_relative_path: Path relative to the corpus root (forward slashes)

        Returns:
            (kind, owner) tuple for the longest matching directory, or None
        """
        path_str = str(Path(repo_relative_path)).replace("\\", "/")

        longest_match: tuple[str, str] | None = None
        longest_length = 0

        for entry in self.entries:
            for directory in entry.directories:
                dir_normalized = directory.replace("\\", "/")
                if path_str == dir_normalized or path_str.startswith(dir_normalized + "/"):
                    if len(dir_normalized) > longest_length:
                        longest_length = len(dir_normalized)
                        longest_match = (entry.kind, entry.owner)

        return longest_match


def _validate_manifest(manifest: CorpusManifest) -> None:
    """Enforce the manifest's structural invariants (fail-loud).

    Raises:
        ManifestValidationError: On unknown owner, a directory covered twice,
            or a reindex root nested inside a harvest directory.
    """
    harvest_dirs: list[str] = []
    reindex_dirs: list[str] = []
    seen_dirs: set[str] = set()

    for entry in manifest.entries:
        if entry.owner not in KNOWN_OWNERS:
            raise ManifestValidationError(
                f"Unknown owner '{entry.owner}' on manifest entry '{entry.kind}': "
                f"known owners are {sorted(KNOWN_OWNERS)}"
            )
        for directory in entry.directories:
            normalized = directory.replace("\\", "/").rstrip("/")
            if normalized in seen_dirs:
                raise ManifestValidationError(
                    f"Directory '{normalized}' is covered twice across manifest entries"
                )
            seen_dirs.add(normalized)
            if entry.owner == "harvest":
                harvest_dirs.append(normalized)
            else:
                reindex_dirs.append(normalized)

    for reindex_dir in reindex_dirs:
        for harvest_dir in harvest_dirs:
            if reindex_dir.startswith(harvest_dir + "/"):
                raise ManifestValidationError(
                    f"Reindex root '{reindex_dir}' is nested inside harvest "
                    f"directory '{harvest_dir}': the same file would be publishable "
                    f"by both pipelines"
                )


def load_manifest(path: Path | str) -> CorpusManifest:
    """Load and validate a corpus manifest JSON file (fail-loud).

    Args:
        path: Path to the manifest JSON (FLEET_MEMORY_CORPUS_MANIFEST)

    Returns:
        Validated CorpusManifest

    Raises:
        ManifestValidationError: On missing schema_version, malformed JSON/shape,
            unknown owner, duplicate directory coverage, or nested reindex roots.
        FileNotFoundError: If the manifest file does not exist.
    """
    manifest_path = Path(path)
    raw_text = manifest_path.read_text(encoding="utf-8")

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ManifestValidationError(f"Manifest {manifest_path} is not valid JSON: {e}") from e

    if not isinstance(raw, dict):
        raise ManifestValidationError(f"Manifest {manifest_path} must be a JSON object")

    if "schema_version" not in raw:
        raise ManifestValidationError(
            f"Manifest {manifest_path} is missing required field: schema_version"
        )

    try:
        manifest = CorpusManifest(**raw)
    except ValidationError as e:
        raise ManifestValidationError(f"Manifest {manifest_path} failed validation: {e}") from e

    _validate_manifest(manifest)
    return manifest
