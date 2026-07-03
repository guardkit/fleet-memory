"""Fixture package providing manifest handling and content hashing.

This module defines:
- ``FixtureError`` base exception and specific error subclasses.
- ``FixtureManifest`` Pydantic model representing the manifest JSON.
- Helper functions ``fixture_dir``, ``compute_content_hash``, ``write_manifest``
  and ``read_manifest``.

All public symbols are re‑exported via ``__all__`` for convenient import:

    from fleet_memory.fixture import (
        FixtureManifest,
        compute_content_hash,
        read_manifest,
        write_manifest,
        UnknownFixtureError,
        FixtureHashMismatchError,
        InvalidCutDateError,
        ScratchNamespaceError,
    )
"""

from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Dict, Mapping

from pydantic import BaseModel, Field, validator

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

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


class FixtureError(Exception):
    """Base class for all fixture‑related errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:  # pragma: no cover – trivial
        return self.message


class UnknownFixtureError(FixtureError):
    """Raised when a fixture directory or its manifest cannot be found."""

    def __init__(self, fixture_id: str) -> None:
        super().__init__(f"Unknown fixture: {fixture_id}")
        self.fixture_id = fixture_id


class FixtureHashMismatchError(FixtureError):
    """Raised when the recomputed content hash does not match the stored hash."""

    def __init__(self, fixture_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Hash mismatch for fixture '{fixture_id}': expected {expected}, got {actual}"
        )
        self.fixture_id = fixture_id
        self.expected = expected
        self.actual = actual


class InvalidCutDateError(FixtureError):
    """Raised when a temporal‑cut date is missing or unparsable."""

    def __init__(self, fixture_id: str, detail: str) -> None:
        super().__init__(f"Invalid cut date for fixture '{fixture_id}': {detail}")
        self.fixture_id = fixture_id
        self.detail = detail


class ScratchNamespaceError(FixtureError):
    """Raised for invalid rollout‑id / scratch‑namespace specifications."""

    def __init__(self, fixture_id: str, detail: str) -> None:
        super().__init__(f"Scratch namespace error for fixture '{fixture_id}': {detail}")
        self.fixture_id = fixture_id
        self.detail = detail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_ID_PATTERN = re.compile(r"^[a-z0-9_.-]+$")
_DEFAULT_ROOT = Path("eval/fixtures")


def fixture_dir(fixtures_root: Path | str = _DEFAULT_ROOT, fixture_id: str = "") -> Path:
    """Return the absolute path for a fixture.

    Args:
        fixtures_root: Base directory containing all fixtures. Defaults to
            ``eval/fixtures`` relative to the current working directory.
        fixture_id: Identifier of the fixture. Must match ``^[a-z0-9_.-]+$`` and be
            non‑empty.

    Raises:
        ValueError: If ``fixture_id`` does not satisfy the required pattern.
    """
    if not fixture_id:
        raise ValueError("fixture_id must be non‑empty")
    if not _FIXTURE_ID_PATTERN.fullmatch(fixture_id):
        raise ValueError(
            f"fixture_id '{fixture_id}' does not match required pattern ^[a-z0-9_.-]+$"
        )
    root = Path(fixtures_root)
    return (root / fixture_id).resolve()


def _payload_files(fixture_path: Path) -> Mapping[Path, bytes]:
    """Return a mapping of relative payload paths to their byte contents.

    ``manifest.json`` is deliberately excluded.
    """
    files: dict[Path, bytes] = {}
    for file_path in sorted(fixture_path.rglob("*")):
        if file_path.is_file():
            rel = file_path.relative_to(fixture_path)
            if rel.name == "manifest.json":
                continue
            files[rel] = file_path.read_bytes()
    return files


def compute_content_hash(fixture_dir: Path | str) -> str:
    """Compute deterministic SHA‑256 hash of all payload files.

    The hash is calculated over the concatenation of each payload file's relative
    path (UTF‑8), a NUL byte, then the file's raw bytes. Files are processed in
    sorted lexical order of their relative paths, guaranteeing determinism across
    runs and independent of filesystem timestamps.
    """
    base = Path(fixture_dir)
    if not base.is_dir():
        raise UnknownFixtureError(str(base))
    hasher = hashlib.sha256()
    payloads = _payload_files(base)
    for rel_path in sorted(payloads):
        hasher.update(rel_path.as_posix().encode())
        hasher.update(b"\x00")
        hasher.update(payloads[rel_path])
    return hasher.hexdigest()

# ---------------------------------------------------------------------------
# Manifest model
# ---------------------------------------------------------------------------


class FixtureManifest(BaseModel):
    """Pydantic model for a fixture manifest.

    Mirrors the JSON schema described in the task specification.
    """

    fixture_id: str = Field(..., pattern=r"^[a-z0-9_.-]+$")
    created_at: str  # ISO‑8601 UTC timestamp (informational only)
    source_target: str  # credential‑free ``host:port/db`` label
    content_hash: str  # SHA‑256 hex digest of payload files
    table_row_counts: Dict[str, int]
    null_occurred_at_count: int
    pg_dump_version: str

    @validator("created_at")
    def _validate_iso8601(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*Z$", v):
            raise ValueError("created_at must be ISO‑8601 UTC ending with 'Z'")
        return v

    @validator("source_target")
    def _validate_source_target(cls, v: str) -> str:
        if "@" in v:
            raise ValueError("source_target must not contain credentials")
        return v

    @validator("content_hash")
    def _validate_hash(cls, v: str) -> str:
        if not re.fullmatch(r"^[a-f0-9]{64}$", v):
            raise ValueError("content_hash must be a SHA‑256 hex digest")
        return v

# ---------------------------------------------------------------------------
# Manifest persistence helpers
# ---------------------------------------------------------------------------

_MANIFEST_NAME = "manifest.json"


def write_manifest(manifest: FixtureManifest, fixture_dir: Path | str) -> None:
    """Write ``manifest`` as JSON with sorted keys and UTF‑8 encoding.

    The file is overwritten if it already exists.
    """
    path = Path(fixture_dir) / _MANIFEST_NAME
    data = manifest.model_dump(mode="json")
    json_str = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    path.write_text(json_str, encoding="utf-8")


def read_manifest(fixture_dir: Path | str) -> FixtureManifest:
    """Read and parse the manifest for ``fixture_dir``.

    Raises:
        UnknownFixtureError: If the directory or ``manifest.json`` is missing.
    """
    base = Path(fixture_dir)
    if not base.is_dir():
        raise UnknownFixtureError(base.name)
    manifest_path = base / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise UnknownFixtureError(base.name)
    content = manifest_path.read_text(encoding="utf-8")
    data = json.loads(content)
    return FixtureManifest(**data)
