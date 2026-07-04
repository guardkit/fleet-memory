"""Per-task temporal-cut filter on ``episode_meta.occurred_at`` (TASK-ABL5-003).

The answer-key leakage control (scope §3.3): for an eval task with a FEAT
start date, ``apply_temporal_cut`` removes from a restored **per-run** store
every entry the on-arm must not see:

1. entries whose ``episode_meta.occurred_at`` is **on or after** the cut
   instant (``>=`` — the boundary instant itself is excluded), and
2. **every** entry whose ``episode_meta.occurred_at`` is NULL or absent
   (distilled build_outcomes/ADRs reference MEM08-era work — answer-key
   risk; 176 such entries on the live store, verified 2026-07-03).

The cut axis is ``value #>> '{episode_meta,occurred_at}'`` — **never the row
``created_at`` column**, which is backfill-era (2026-06-28 onward): an entry
ingested during the backfill but describing 2026-05 work must survive a
2026-06-25 cut. No SQL in this module references ``created_at``.

Deletion is transactional and covers the search index: ``store_vectors`` rows
for excluded entries are deleted explicitly, before their ``store`` rows, in
the same transaction. (The langgraph schema's ``store_vectors`` FK is
``ON DELETE CASCADE`` — verified against the installed
langgraph-checkpoint-postgres — but the explicit delete makes the no-orphans
guarantee structural rather than schema-dependent.)

This module never runs against the live store by design of its callers; it
never constructs a DSN itself — it acts on the (per-run) DSN it is given.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fleet_memory.fixture import FixtureError, InvalidCutDateError
from fleet_memory.fixture.dsn import sanitize_target, scrub_secrets
from fleet_memory.fixture.snapshot import _default_connect

__all__ = [
    "AFTER_CUT_PREDICATE",
    "COUNT_AFTER_CUT_SQL",
    "COUNT_NULL_SQL",
    "COUNT_TOTAL_SQL",
    "DELETE_STORE_SQL",
    "DELETE_VECTORS_SQL",
    "NULL_PREDICATE",
    "SESSION_SQL",
    "CutResult",
    "apply_temporal_cut",
    "normalize_cut",
]

# Session timezone is pinned so that any stored occurred_at ISO string lacking
# an explicit UTC offset is still cast to timestamptz as UTC, not server-local.
SESSION_SQL = "SET TIME ZONE 'UTC'"


def _occurred_at_expr(value_ref: str = "value") -> str:
    """The cut axis: JSONB path extraction of the entry's own occurred_at."""
    return f"{value_ref} #>> '{{episode_meta,occurred_at}}'"


def _after_cut_predicate(value_ref: str = "value") -> str:
    """occurred_at >= cut instant; the cut value is a bind parameter, never inlined."""
    return f"({_occurred_at_expr(value_ref)})::timestamptz >= %(cut)s"


def _null_predicate(value_ref: str = "value") -> str:
    """Covers JSON null, absent occurred_at key, and absent episode_meta entirely."""
    return f"({_occurred_at_expr(value_ref)}) IS NULL"


def _excluded_predicate(value_ref: str = "value") -> str:
    return f"({_after_cut_predicate(value_ref)} OR {_null_predicate(value_ref)})"


AFTER_CUT_PREDICATE = _after_cut_predicate()
NULL_PREDICATE = _null_predicate()

COUNT_AFTER_CUT_SQL = f'SELECT count(*) FROM "public"."store" WHERE {AFTER_CUT_PREDICATE}'
COUNT_NULL_SQL = f'SELECT count(*) FROM "public"."store" WHERE {NULL_PREDICATE}'
COUNT_TOTAL_SQL = 'SELECT count(*) FROM "public"."store"'

# Vectors first (the join needs the store rows still present), store second,
# both in the same transaction — no store_vectors row may outlive its entry.
DELETE_VECTORS_SQL = (
    'DELETE FROM "public"."store_vectors" AS v USING "public"."store" AS s '
    f"WHERE v.prefix = s.prefix AND v.key = s.key AND {_excluded_predicate('s.value')}"
)
DELETE_STORE_SQL = f'DELETE FROM "public"."store" WHERE {_excluded_predicate()}'


@dataclass(frozen=True)
class CutResult:
    """Outcome of a temporal cut (all counts over the ``store`` table)."""

    excluded_after_cut: int  # occurred_at >= cut instant
    excluded_null: int  # occurred_at NULL/absent
    remaining: int  # store rows left after the cut


def normalize_cut(cut: object) -> datetime:
    """Normalise ``cut`` to a timezone-aware ``datetime``.

    Accepts a ``date`` (midnight UTC at the start of that date), an aware
    ``datetime``, or an ISO-8601 string parsing to one of those. Everything
    else — ``None``, empty/garbage strings, naive datetimes, other types —
    raises :class:`InvalidCutDateError`: a cut that silently skips leakage
    control is worse than no cut.
    """
    if isinstance(cut, datetime):  # before date: datetime subclasses date
        if cut.tzinfo is None or cut.tzinfo.utcoffset(cut) is None:
            raise InvalidCutDateError(
                f"naive datetime {cut.isoformat()!r}; the cut instant must be timezone-aware"
            )
        return cut
    if isinstance(cut, date):
        return datetime(cut.year, cut.month, cut.day, tzinfo=UTC)
    if isinstance(cut, str):
        text = cut.strip()
        if not text:
            raise InvalidCutDateError("empty cut value")
        try:
            return normalize_cut(date.fromisoformat(text))
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise InvalidCutDateError(f"unparsable cut value {text!r}") from None
        return normalize_cut(parsed)
    raise InvalidCutDateError(f"unsupported cut type {type(cut).__name__!r}")


def apply_temporal_cut(
    target_dsn: str,
    cut: date | datetime | str,
    *,
    dry_run: bool = False,
    connection_factory: Callable[[str], Any] | None = None,
) -> CutResult:
    """Apply the temporal cut to the per-run store at ``target_dsn``.

    Counts entries excluded by the cut instant and by NULL/absent
    ``occurred_at``, then (unless ``dry_run``) deletes them and their
    ``store_vectors`` rows in one transaction. Idempotent: re-applying the
    same cut reports ``CutResult(0, 0, remaining)`` and changes nothing.
    ``dry_run=True`` never deletes — it is the operator/validation preview.
    """
    # Normalising first means an invalid cut can never touch the store.
    cut_at = normalize_cut(cut)
    params = {"cut": cut_at}

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
            cur.execute(SESSION_SQL)
            cur.execute(COUNT_AFTER_CUT_SQL, params)
            excluded_after_cut = int(cur.fetchone()[0])
            cur.execute(COUNT_NULL_SQL)
            excluded_null = int(cur.fetchone()[0])

            if dry_run:
                cur.execute(COUNT_TOTAL_SQL)
                total = int(cur.fetchone()[0])
                conn.rollback()
                return CutResult(
                    excluded_after_cut=excluded_after_cut,
                    excluded_null=excluded_null,
                    remaining=total - excluded_after_cut - excluded_null,
                )

            cur.execute(DELETE_VECTORS_SQL, params)
            cur.execute(DELETE_STORE_SQL, params)
            cur.execute(COUNT_TOTAL_SQL)
            remaining = int(cur.fetchone()[0])
            conn.commit()
            return CutResult(
                excluded_after_cut=excluded_after_cut,
                excluded_null=excluded_null,
                remaining=remaining,
            )
        except FixtureError:
            raise
        except Exception as exc:
            detail = scrub_secrets(str(exc), target_dsn)
            raise FixtureError(f"Temporal cut on {target} failed: {detail}") from None
    finally:
        conn.close()
