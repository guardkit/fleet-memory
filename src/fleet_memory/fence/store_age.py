"""How old is the newest thing memory learned? A read-only look at the store.

Deliberate choices, each load-bearing:

* **Read-only session, raw psycopg.** ``async_store_context`` runs ``store.setup()``
  — DDL, a write — and needs embed config. A watchdog must never be able to change
  what it watches, so the session sets ``default_transaction_read_only = on`` first,
  exactly as the fixture snapshot path does.
* **``updated_at``, not ``created_at``.** langgraph bumps ``updated_at`` on every real
  upsert (``ON CONFLICT ... updated_at = CURRENT_TIMESTAMP``) and it is always at or
  after ``created_at``. ``created_at`` is reported alongside as a cross-check only.
* **Never ``episode_meta.occurred_at``.** That is *event* time, deliberately decoupled
  from row time, and most live rows do not carry it. It answers a different question.
* **An unreachable store is an ALARM, not a crash.** This is the point of the rung:
  the Chronicler failed three scheduled runs in a row on a Postgres connection timeout
  and nothing surfaced it. The fence is the thing that surfaces it, so it must survive
  the failure long enough to report it.

No DSN, no password, and no environment value ever leaves this module: hosts are
labelled through ``sanitize_target`` and every error text passes ``scrub_secrets``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fleet_memory.fixture.dsn import sanitize_target, scrub_secrets

__all__ = [
    "PROJECT_AGE_SQL",
    "READ_ONLY_SESSION_SQL",
    "STORE_AGE_SQL",
    "ProjectFacts",
    "StoreFacts",
    "project_patterns",
    "read_store_facts",
]

#: Read-only + UTC. Read-only makes "the fence never writes" structural, not a promise.
#
# ORDER AND CONTENT ARE BOTH LOAD-BEARING. ``default_transaction_read_only`` only
# affects transactions started *after* it is set — and psycopg opens a transaction on
# the first statement, so on its own it leaves the very transaction the fence runs in
# fully writable. (The integration test in tests/integration/test_fence_store_age.py
# caught exactly that: an INSERT succeeded.) ``SET TRANSACTION READ ONLY`` must
# therefore come first, marking the current transaction, with the default setting kept
# as a belt-and-braces for any later one.
READ_ONLY_SESSION_SQL: tuple[str, ...] = (
    "SET TRANSACTION READ ONLY",
    "SET default_transaction_read_only = on",
    "SET TIME ZONE 'UTC'",
)

NAMESPACE_ROOT = "fleet_memory"

# Both operands are bind parameters — a project name never reaches SQL text.
# ESCAPE '\' pins the escape character used when building the LIKE operand, so an
# underscore in a project name cannot act as a single-character wildcard.
_MATCH_CLAUSE = "prefix = %(prefix)s OR prefix LIKE %(pattern)s ESCAPE '\\'"

STORE_AGE_SQL = 'SELECT max(updated_at), max(created_at), count(*) FROM "public"."store"'
PROJECT_AGE_SQL = (
    'SELECT max(updated_at), max(created_at), count(*) FROM "public"."store" '
    f"WHERE {_MATCH_CLAUSE}"
)


@dataclass(frozen=True)
class ProjectFacts:
    """Newest row and row count for one watched project."""

    project: str
    newest_updated_at: datetime | None
    newest_created_at: datetime | None
    row_count: int


@dataclass(frozen=True)
class StoreFacts:
    """What the store says about its own freshness.

    ``reachable`` false with a ``problem`` string is a normal, expected outcome —
    it becomes a STORE_UNREACHABLE alarm rather than a traceback.
    """

    target: str
    reachable: bool
    newest_updated_at: datetime | None = None
    newest_created_at: datetime | None = None
    row_count: int = 0
    per_project: tuple[ProjectFacts, ...] = ()
    problem: str | None = None
    detail: dict = field(default_factory=dict)


def project_patterns(project: str) -> tuple[str, str]:
    """(exact prefix, escaped LIKE operand) selecting only that project's rows.

    Namespaces persist as dot-joined ``prefix`` text, so a project's rows live under
    ``fleet_memory.<project>`` and ``fleet_memory.<project>.<payload_type>``.
    """
    exact = f"{NAMESPACE_ROOT}.{project}"
    escaped = exact.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")
    return exact, f"{escaped}.%"


def _default_connect(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn)


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def read_store_facts(
    dsn: str,
    projects: Sequence[str] = (),
    *,
    connection_factory: Callable[[str], Any] | None = None,
) -> StoreFacts:
    """Read freshness facts from the store. Never raises — failure becomes a fact.

    Args:
        dsn: Postgres DSN (from the environment only; never from argv).
        projects: Extra projects to measure individually, on top of the whole store.
        connection_factory: Injectable connect seam, so tests never need a database.
    """
    target = sanitize_target(dsn)
    connect = connection_factory or _default_connect

    try:
        conn = connect(dsn)
    except Exception as exc:
        detail = scrub_secrets(str(exc), dsn).strip()
        return StoreFacts(
            target=target,
            reachable=False,
            problem=f"cannot reach the memory store at {target} ({detail or type(exc).__name__})",
        )

    try:
        cur = conn.cursor()
        for statement in READ_ONLY_SESSION_SQL:
            cur.execute(statement)

        cur.execute(STORE_AGE_SQL)
        row = cur.fetchone()
        newest_updated = _as_utc(row[0]) if row else None
        newest_created = _as_utc(row[1]) if row else None
        row_count = int(row[2]) if row else 0

        per_project: list[ProjectFacts] = []
        for project in projects:
            exact, pattern = project_patterns(project)
            cur.execute(PROJECT_AGE_SQL, {"prefix": exact, "pattern": pattern})
            prow = cur.fetchone()
            per_project.append(
                ProjectFacts(
                    project=project,
                    newest_updated_at=_as_utc(prow[0]) if prow else None,
                    newest_created_at=_as_utc(prow[1]) if prow else None,
                    row_count=int(prow[2]) if prow else 0,
                )
            )

        return StoreFacts(
            target=target,
            reachable=True,
            newest_updated_at=newest_updated,
            newest_created_at=newest_created,
            row_count=row_count,
            per_project=tuple(per_project),
        )
    except Exception as exc:
        detail = scrub_secrets(str(exc), dsn).strip()
        return StoreFacts(
            target=target,
            reachable=False,
            problem=(
                f"the memory store at {target} could not be queried "
                f"({detail or type(exc).__name__})"
            ),
        )
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover - close failures are not worth an alarm
            pass
