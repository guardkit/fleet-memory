"""Fixture package providing manifest handling, content hashing, and error taxonomy.

Public API re-exports:
- FixtureManifest
- compute_content_hash
- write_manifest
- read_manifest
- fixture_dir
- UnknownFixtureError, FixtureHashMismatchError, InvalidCutDateError, ScratchNamespaceError
"""

from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, Field, ValidationError, validator

__all__ = [
    "FixtureError",
    "UnknownFixtureError",
    "FixtureHashMismatchError",
    "InvalidCutDateError",
    "ScratchNamespaceError",
    "FixtureManifest",
    "fixture_dir",
    "compute_content_hash",
    "write_manifest",
    "read_manifest",
]

# ----- Error taxonomy -----

class FixtureError(Exception):
    """Base class for all fixture package errors."""


class UnknownFixtureError(FixtureError):
    """Raised when a fixture directory or its manifest cannot be found."""

    def __init__(self, fixture_id: str) -> None:
        super().__init__(f"Unknown fixture '{fixture_id}'")
        self.fixture_id = fixture_id


class FixtureHashMismatchError(FixtureError):
    """Raised when a recomputed content hash differs from the manifest hash."""

    def __init__(self, fixture_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Fixture '{fixture_id}' hash mismatch: expected {expected}, got {actual}"
        )
        self.fixture_id = fixture_id
        self.expected = expected
        self.actual = actual


class InvalidCutDateError(FixtureError):
    """Raised when a temporal‑cut date is missing or unparsable."""

    def __init__(self, detail: str | None = None) -> None:
        msg = "Invalid cut date"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
        self.detail = detail


class ScratchNamespaceError(FixtureError):
    """Raised for invalid rollout‑id / scratch namespace values."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"Invalid scratch namespace: {detail}")
        self.detail = detail

# ----- Manifest model -----

_fixture_id_regex = re.compile(r"^[a-z0-9_.-]+$")


class FixtureManifest(BaseModel):
    """Pydantic model representing a fixture manifest.

    Fields correspond to the specification in TASK‑ABL5‑001.
    """

    fixture_id: str = Field(..., description="Identifier matching ^[a-z0-9_.-]+$")
    created_at: str = Field(..., description="ISO‑8601 UTC timestamp (informational)")
    source_target: str = Field(..., description="Credential‑free host:port/db label")
    content_hash: str = Field(..., description="SHA‑256 hex digest of payload files")
    table_row_counts: Dict[str, int] = Field(default_factory=dict)
    null_occurred_at_count: int = 0
    pg_dump_version: str = ""

    @validator("fixture_id")
    def validate_fixture_id(cls, v: str) -> str:
        if not _fixture_id_regex.fullmatch(v):
            raise ValueError(
                f"fixture_id '{v}' does not match required pattern ^[a-z0-9_.-]+$"
            )
        return v

    class Config:
        frozen = True
        arbitrary_types_allowed = True

# ----- Helper functions -----

def fixture_dir(fixtures_root: Path | str, fixture_id: str) -> Path:
    """Return the absolute path for a fixture.

    Raises ``ValueError`` if ``fixture_id`` fails the required pattern or attempts
    path traversal.
    """

    if not _fixture_id_regex.fullmatch(fixture_id):
        raise ValueError(f"Invalid fixture_id '{fixture_id}'")
    # Resolve to ensure no ``..`` components affect the path
    candidate = (fixtures_root / fixture_id).resolve()
    if not str(candidate).startswith(str(fixtures_root.resolve())):
        raise ValueError("fixture_id results in path traversal")
    return candidate


def compute_content_hash(fixture_dir: Path) -> str:
    """Compute a deterministic SHA‑256 hash of all payload files.

    The hash is calculated over the concatenation of each file's relative path
    (UTF‑8) followed by a NUL byte and the file's raw bytes. Files are processed
    in sorted relative‑path order. ``manifest.json`` is excluded.
    """

    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"Fixture directory not found: {fixture_dir}")

    hash_obj = hashlib.sha256()
    for file_path in sorted(
        p for p in fixture_dir.rglob("*") if p.is_file() and p.name != "manifest.json"
    ):
        rel_path = file_path.relative_to(fixture_dir).as_posix()
        hash_obj.update(rel_path.encode("utf-8"))
        hash_obj.update(b"\x00")
        hash_obj.update(file_path.read_bytes())
    return hash_obj.hexdigest()


def write_manifest(manifest: FixtureManifest, fixture_dir: Path) -> None:
    """Write ``manifest`` as ``manifest.json`` inside ``fixture_dir``.

    The JSON is written with UTF‑8 encoding, sorted keys and no extra whitespace.
    """

    fixture_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = fixture_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(
            manifest.model_dump(), f, ensure_ascii=False, sort_keys=True, indent=2
        )


def read_manifest(fixture_dir: Path) -> FixtureManifest:
    """Read and parse ``manifest.json`` from ``fixture_dir``.

    Raises ``UnknownFixtureError`` if the directory or manifest file is missing.
    """

    manifest_path = fixture_dir / "manifest.json"
    if not manifest_path.is_file():
        raise UnknownFixtureError(fixture_dir.name)
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        return FixtureManifest(**data)
    except ValidationError as exc:
        raise FixtureError(str(exc)) from exc
