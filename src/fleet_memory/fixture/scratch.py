"""Scratch namespace lifecycle for rollout-time writes (TASK-ABL5-004).

Scope §3.3: the fixture corpus is mounted read-only; every rollout-time write
goes to a scratch namespace that is discarded after the rollout. Store
namespaces are ``("fleet_memory", <project>, <payload_type>)`` tuples persisted
as dot-joined ``prefix`` text (validated ``^[a-z0-9_]+$`` per segment by
``fleet_memory.store.validate_namespace``). Retrieval matches the project
segment exactly (``_matches_project``), so a scratch **project** segment
``scratch_<rollout_id>`` is invisible to corpus retrieval by construction.

This module only names scratch namespaces and discards them — the rollout's
own store client performs the writes via ``scratch_namespace(...)``; nothing
here wraps ``store.aput``.

Guard rails:

* Rollout ids are validated (never silently sanitised — a mangled id would
  orphan the discard): ``scratch_project`` raises
  :class:`~fleet_memory.fixture.ScratchNamespaceError` unless
  ``scratch_<rollout_id>`` matches ``^[a-z0-9_]+$``. Validation happens
  BEFORE any SQL pattern is built or any connection is opened, so a malformed
  pattern can never widen a delete.
* The dotted-prefix ``LIKE`` operand escapes every LIKE metacharacter in the
  literal part (``ESCAPE '\\'``), so ``_`` in an id can never act as a
  single-character wildcard: ``discard_scratch(dsn, "run1")`` cannot touch a
  corpus project like ``guardkit`` or a sibling scratch project
  ``scratch_run2`` / ``scratch_run12``.
* ``store_vectors`` rows for the scratch project are deleted in the same
  transaction, before their ``store`` rows.

This module never runs against the live store by design of its callers; it
acts only on the (per-run) DSN it is given.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from fleet_memory.fixture import FixtureError, ScratchNamespaceError
from fleet_memory.fixture.dsn import sanitize_target, scrub_secrets
from fleet_memory.fixture.snapshot import _default_connect

__all__ = [
    "DISCARD_STORE_SQL",
    "DISCARD_VECTORS_SQL",
    "LIST_PREFIXES_SQL",
    "NAMESPACE_ROOT",
    "SCRATCH_PREFIX",
    "discard_patterns",
    "discard_scratch",
    "list_scratch_projects",
    "scratch_namespace",
    "scratch_project",
]

NAMESPACE_ROOT = "fleet_memory"
SCRATCH_PREFIX = "scratch_"

# Mirrors the store's namespace-segment rule (src/fleet_memory/store.py:26,
# validate_namespace). Kept local so this naming/discard helper does not pull
# in the store's langgraph import chain; the unit suite asserts compatibility
# against the public validate_namespace.
_SEGMENT_PATTERN = re.compile(r"^[a-z0-9_]+$")

# Both operands are bind parameters — the rollout id never reaches SQL text.
# ESCAPE '\' pins the escape character so the escaped LIKE operand built by
# discard_patterns() is interpreted the way it was constructed.
_MATCH_CLAUSE = "prefix = %(prefix)s OR prefix LIKE %(pattern)s ESCAPE '\\'"

# Vectors first (while their store rows still exist), store second, one
# transaction — no store_vectors row may outlive its entry.
DISCARD_VECTORS_SQL = f'DELETE FROM "public"."store_vectors" WHERE {_MATCH_CLAUSE}'
DISCARD_STORE_SQL = f'DELETE FROM "public"."store" WHERE {_MATCH_CLAUSE}'
LIST_PREFIXES_SQL = 'SELECT DISTINCT prefix FROM "public"."store"'


def scratch_project(rollout_id: str) -> str:
    """Return the scratch project segment ``scratch_<rollout_id>``.

    Raises :class:`ScratchNamespaceError` if ``rollout_id`` is not a
    non-empty ``^[a-z0-9_]+$`` string. Nothing is silently rewritten: a
    sanitised id would name a different project than the rollout wrote to,
    orphaning the discard.
    """
    if not isinstance(rollout_id, str):
        raise ScratchNamespaceError(f"rollout_id must be a string, got {type(rollout_id).__name__}")
    if not rollout_id:
        raise ScratchNamespaceError("rollout_id is empty")
    project = SCRATCH_PREFIX + rollout_id
    if not _SEGMENT_PATTERN.fullmatch(project):
        raise ScratchNamespaceError(
            f"rollout_id {rollout_id!r} does not produce a valid project segment"
            " (^[a-z0-9_]+$); refusing to sanitise it silently"
        )
    return project


def scratch_namespace(rollout_id: str, payload_type: str) -> tuple[str, str, str]:
    """Namespace tuple for a rollout's writes: ``("fleet_memory", scratch_<id>, <payload_type>)``.

    The returned tuple always passes ``fleet_memory.store.validate_namespace``;
    an invalid ``payload_type`` raises :class:`ScratchNamespaceError` here
    rather than failing later at write time.
    """
    project = scratch_project(rollout_id)
    if not isinstance(payload_type, str) or not _SEGMENT_PATTERN.fullmatch(payload_type):
        raise ScratchNamespaceError(
            f"payload_type {payload_type!r} is not a valid namespace segment (^[a-z0-9_]+$)"
        )
    return (NAMESPACE_ROOT, project, payload_type)


def discard_patterns(rollout_id: str) -> tuple[str, str]:
    """(exact prefix, escaped LIKE operand) selecting only the scratch project's rows.

    The exact operand matches a row stored under the bare 2-tuple namespace;
    the LIKE operand matches ``fleet_memory.scratch_<id>.<anything>``. Every
    LIKE metacharacter in the literal part is escaped with ``\\`` so ``_``
    never acts as a wildcard — sibling projects sharing the id as a prefix
    (``scratch_run12`` for ``run1``) and corpus projects cannot match.
    """
    exact = f"{NAMESPACE_ROOT}.{scratch_project(rollout_id)}"
    escaped = exact.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")
    return exact, f"{escaped}.%"


def discard_scratch(
    target_dsn: str,
    rollout_id: str,
    *,
    connection_factory: Callable[[str], Any] | None = None,
) -> int:
    """Delete every row of the rollout's scratch project from the store.

    Removes matching ``store_vectors`` rows and ``store`` rows in one
    transaction and returns the number of ``store`` rows deleted. Idempotent:
    a second call returns 0. An invalid ``rollout_id`` raises
    :class:`ScratchNamespaceError` before any connection is opened.
    """
    # Validation + pattern construction first: an invalid id can never
    # produce a pattern, let alone touch the store.
    exact, pattern = discard_patterns(rollout_id)
    params = {"prefix": exact, "pattern": pattern}

    target = sanitize_target(target_dsn)
    connect = connection_factory or _default_connect
    try:
        conn = connect(target_dsn)
    except Exception as exc:
        detail = scrub_secrets(str(exc), target_dsn)
        raise FixtureError(f"Cannot connect to {target}: {detail}") from None

    try:
        try:
            cur = conn.cursor()
            cur.execute(DISCARD_VECTORS_SQL, params)
            cur.execute(DISCARD_STORE_SQL, params)
            deleted = int(cur.rowcount)
            conn.commit()
            return deleted
        except FixtureError:
            raise
        except Exception as exc:
            detail = scrub_secrets(str(exc), target_dsn)
            raise FixtureError(f"Scratch discard on {target} failed: {detail}") from None
    finally:
        conn.close()


def list_scratch_projects(
    target_dsn: str,
    *,
    connection_factory: Callable[[str], Any] | None = None,
) -> list[str]:
    """Distinct ``scratch_*`` project segments present in the store, sorted.

    Lets the rollout adapter assert "no scratch residue" before an arm
    starts. Only prefixes rooted at ``fleet_memory`` whose project segment
    starts with ``scratch_`` are reported; corpus projects are ignored.
    """
    target = sanitize_target(target_dsn)
    connect = connection_factory or _default_connect
    try:
        conn = connect(target_dsn)
    except Exception as exc:
        detail = scrub_secrets(str(exc), target_dsn)
        raise FixtureError(f"Cannot connect to {target}: {detail}") from None

    try:
        try:
            cur = conn.cursor()
            cur.execute(LIST_PREFIXES_SQL)
            rows = cur.fetchall()
            conn.rollback()  # read-only
        except FixtureError:
            raise
        except Exception as exc:
            detail = scrub_secrets(str(exc), target_dsn)
            raise FixtureError(f"Scratch listing on {target} failed: {detail}") from None
    finally:
        conn.close()

    projects: set[str] = set()
    for (prefix,) in rows:
        parts = prefix.split(".")
        if len(parts) >= 2 and parts[0] == NAMESPACE_ROOT and parts[1].startswith(SCRATCH_PREFIX):
            projects.add(parts[1])
    return sorted(projects)
