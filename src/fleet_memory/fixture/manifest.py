"""Alias module exposing the TASK-ABL5-001 manifest API as ``fleet_memory.fixture.manifest``.

The manifest model, content-hash, and IO helpers were implemented in the
package ``__init__`` (TASK-ABL5-001); downstream contracts import them from
this module path.
"""

from fleet_memory.fixture import (
    FixtureError,
    FixtureHashMismatchError,
    FixtureManifest,
    UnknownFixtureError,
    compute_content_hash,
    fixture_dir,
    read_manifest,
    write_manifest,
)

__all__ = [
    "FixtureError",
    "FixtureHashMismatchError",
    "FixtureManifest",
    "UnknownFixtureError",
    "compute_content_hash",
    "fixture_dir",
    "read_manifest",
    "write_manifest",
]
