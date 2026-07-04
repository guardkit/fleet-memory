"""Unit tests for fleet_memory.fixture.temporal_cut (TASK-ABL5-003).

No Docker/Postgres: SQL/predicate construction and cut-value normalisation are
tested pure; the database side is an injected fake connection seam that
scripts count results and records every statement. Seeded-store behaviour
(FEAT-HARV / OUT-SMOKE / 176-null acceptance proof) is TASK-ABL5-006's
integration suite.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from fleet_memory.fixture import FixtureError, InvalidCutDateError
from fleet_memory.fixture.temporal_cut import (
    AFTER_CUT_PREDICATE,
    COUNT_AFTER_CUT_SQL,
    COUNT_NULL_SQL,
    COUNT_TOTAL_SQL,
    DELETE_STORE_SQL,
    DELETE_VECTORS_SQL,
    NULL_PREDICATE,
    SESSION_SQL,
    CutResult,
    apply_temporal_cut,
    normalize_cut,
)
from tests.unit.fixture.fakes import refusing_connection_factory

PASSWORD = "S3cr3tPW"
DSN = f"postgresql://runner:{PASSWORD}@runhost:5544/perrun"

ALL_SQL = (
    SESSION_SQL,
    COUNT_AFTER_CUT_SQL,
    COUNT_NULL_SQL,
    COUNT_TOTAL_SQL,
    DELETE_VECTORS_SQL,
    DELETE_STORE_SQL,
)


# ----- fake connection seam -----


class FakeCutCursor:
    def __init__(self, db: FakeCutDatabase) -> None:
        self._db = db
        self._row: tuple | None = None

    def execute(self, sql: str, params=None) -> None:
        self._db.executed.append((sql, params))
        if self._db.fail_on and self._db.fail_on in sql:
            raise RuntimeError(f"query failed on {DSN} (password={PASSWORD})")
        if sql == COUNT_AFTER_CUT_SQL:
            self._row = (self._db.after_cut,)
        elif sql == COUNT_NULL_SQL:
            self._row = (self._db.null,)
        elif sql == COUNT_TOTAL_SQL:
            self._row = (self._db.current_total(),)
        elif sql == DELETE_VECTORS_SQL:
            self._db.deleted_vectors = True
            self._row = None
        elif sql == DELETE_STORE_SQL:
            self._db.deleted_store = True
            self._row = None
        else:
            self._row = None

    def fetchone(self):
        return self._row


class FakeCutConnection:
    def __init__(self, db: FakeCutDatabase) -> None:
        self._db = db

    def cursor(self) -> FakeCutCursor:
        return FakeCutCursor(self._db)

    def commit(self) -> None:
        self._db.committed = True

    def rollback(self) -> None:
        self._db.rolled_back = True

    def close(self) -> None:
        self._db.closed = True


class FakeCutDatabase:
    """Scripted store state: counts before the cut, delete tracking after."""

    def __init__(
        self,
        *,
        after_cut: int = 0,
        null: int = 0,
        total: int = 0,
        fail_on: str | None = None,
    ) -> None:
        self.after_cut = after_cut
        self.null = null
        self.total = total
        self.fail_on = fail_on
        self.executed: list[tuple[str, object]] = []
        self.deleted_vectors = False
        self.deleted_store = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def current_total(self) -> int:
        if self.deleted_store:
            return self.total - self.after_cut - self.null
        return self.total

    def connection_factory(self, dsn: str) -> FakeCutConnection:
        self.connected_dsn = dsn
        return FakeCutConnection(self)


# ----- cut-value normalisation -----


def test_date_means_midnight_utc():
    assert normalize_cut(date(2026, 6, 25)) == datetime(2026, 6, 25, tzinfo=UTC)


def test_aware_datetime_passes_through_unchanged():
    cut = datetime(2026, 6, 25, 14, 30, tzinfo=UTC)
    assert normalize_cut(cut) is cut


def test_aware_non_utc_datetime_keeps_its_instant():
    tz = timezone(timedelta(hours=2))
    cut = datetime(2026, 6, 25, 14, 30, tzinfo=tz)
    assert normalize_cut(cut) == datetime(2026, 6, 25, 12, 30, tzinfo=UTC)


def test_iso_date_string_means_midnight_utc():
    assert normalize_cut("2026-06-25") == datetime(2026, 6, 25, tzinfo=UTC)


@pytest.mark.parametrize("suffix", ["+00:00", "Z"])
def test_iso_datetime_string_with_offset_is_aware(suffix: str):
    assert normalize_cut(f"2026-06-25T14:00:00{suffix}") == datetime(2026, 6, 25, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "not-a-date",
        "2026-13-40",
        "2026-06-25T14:00:00",  # naive datetime string
        datetime(2026, 6, 25, 14, 0),  # naive datetime
        42,
        3.14,
        b"2026-06-25",
        ["2026-06-25"],
    ],
)
def test_invalid_cut_values_are_rejected(bad):
    with pytest.raises(InvalidCutDateError):
        normalize_cut(bad)


# ----- SQL construction -----


def test_predicates_target_occurred_at_path_with_boundary_excluded():
    # The cut axis is the entry's own occurred_at inside the JSONB value.
    assert "value #>> '{episode_meta,occurred_at}'" in AFTER_CUT_PREDICATE
    assert "value #>> '{episode_meta,occurred_at}'" in NULL_PREDICATE
    # >= : the boundary instant itself is excluded.
    assert ">= %(cut)s" in AFTER_CUT_PREDICATE
    assert "IS NULL" in NULL_PREDICATE


def test_no_sql_references_created_at():
    for sql in ALL_SQL:
        assert "created_at" not in sql


def test_delete_statements_cover_both_exclusion_branches():
    for sql in (DELETE_VECTORS_SQL, DELETE_STORE_SQL):
        assert ">= %(cut)s" in sql
        assert "IS NULL" in sql
    # Vector deletion joins the search index to its store rows.
    assert '"public"."store_vectors"' in DELETE_VECTORS_SQL
    assert "v.prefix = s.prefix AND v.key = s.key" in DELETE_VECTORS_SQL


def test_cut_value_is_parameterised_never_interpolated():
    db = FakeCutDatabase(after_cut=3, null=176, total=1356)
    cut = datetime(2026, 6, 25, tzinfo=UTC)
    apply_temporal_cut(DSN, cut, connection_factory=db.connection_factory)
    for sql, params in db.executed:
        assert "2026" not in sql  # the cut instant never appears in SQL text
        if "%(cut)s" in sql:
            assert params == {"cut": cut}


# ----- behaviour via the fake seam -----


def test_apply_deletes_vectors_then_store_in_order_and_commits():
    db = FakeCutDatabase(after_cut=30, null=176, total=1356)
    result = apply_temporal_cut(DSN, "2026-06-25", connection_factory=db.connection_factory)

    assert result == CutResult(excluded_after_cut=30, excluded_null=176, remaining=1150)
    statements = [sql for sql, _ in db.executed]
    assert statements[0] == SESSION_SQL  # UTC session pinned before any query
    assert statements.index(DELETE_VECTORS_SQL) < statements.index(DELETE_STORE_SQL)
    assert db.committed
    assert not db.rolled_back
    assert db.closed


def test_dry_run_never_deletes():
    db = FakeCutDatabase(after_cut=30, null=176, total=1356)
    result = apply_temporal_cut(
        DSN, date(2026, 6, 25), dry_run=True, connection_factory=db.connection_factory
    )

    assert result == CutResult(excluded_after_cut=30, excluded_null=176, remaining=1150)
    statements = [sql for sql, _ in db.executed]
    assert not any(sql.startswith("DELETE") for sql in statements)
    assert not db.deleted_vectors
    assert not db.deleted_store
    assert not db.committed
    assert db.closed


def test_reapplying_same_cut_is_a_noop_reporting_zero():
    # State after a previous identical cut: nothing left matches either branch.
    db = FakeCutDatabase(after_cut=0, null=0, total=1150)
    result = apply_temporal_cut(DSN, "2026-06-25", connection_factory=db.connection_factory)
    assert result == CutResult(excluded_after_cut=0, excluded_null=0, remaining=1150)


def test_null_only_cut_counts_separately():
    db = FakeCutDatabase(after_cut=0, null=176, total=1356)
    result = apply_temporal_cut(DSN, "2026-06-25", connection_factory=db.connection_factory)
    assert result.excluded_after_cut == 0
    assert result.excluded_null == 176
    assert result.remaining == 1180


def test_invalid_cut_never_touches_the_store():
    with pytest.raises(InvalidCutDateError):
        apply_temporal_cut(DSN, None, connection_factory=refusing_connection_factory)
    with pytest.raises(InvalidCutDateError):
        apply_temporal_cut(
            DSN,
            datetime(2026, 6, 25),  # naive
            dry_run=True,
            connection_factory=refusing_connection_factory,
        )


# ----- credential hygiene -----


def test_connect_failure_never_leaks_password():
    def failing_factory(dsn: str):
        raise RuntimeError(f"could not connect using {dsn} (password={PASSWORD})")

    with pytest.raises(FixtureError) as excinfo:
        apply_temporal_cut(DSN, "2026-06-25", connection_factory=failing_factory)
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "runhost:5544/perrun" in message


def test_query_failure_is_scrubbed_and_connection_closed():
    db = FakeCutDatabase(after_cut=1, null=2, total=3, fail_on="DELETE")
    with pytest.raises(FixtureError) as excinfo:
        apply_temporal_cut(DSN, "2026-06-25", connection_factory=db.connection_factory)
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "runhost:5544/perrun" in message
    assert not db.committed
    assert db.closed
