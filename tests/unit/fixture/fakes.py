"""Fake psycopg-connection and pg_dump seams for TASK-ABL5-002 unit tests.

No Docker/Postgres: `create_snapshot` and `restore_fixture` take injected
`connection_factory` / `pg_dump_runner` seams; these fakes script the catalog
responses and record every statement for assertion.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

_TABLE_RE = re.compile(r'"public"\."([^"]+)"')


def pg_dump_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


class RecordingPgDump:
    """pg_dump seam that records argv/env and returns a canned result."""

    def __init__(self, result: SimpleNamespace) -> None:
        self.result = result
        self.calls: list[tuple[list[str], dict | None]] = []

    def __call__(self, args, env=None):
        self.calls.append((list(args), env))
        return self.result


class FakeCopyOut:
    """Context manager mimicking psycopg's COPY ... TO STDOUT read side."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __iter__(self):
        return iter(self._chunks)


class FakeCopyIn:
    """Context manager mimicking psycopg's COPY ... FROM STDIN write side."""

    def __init__(self, db: FakeDatabase, table: str) -> None:
        self._db = db
        self._table = table

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def write(self, data: bytes) -> None:
        self._db.copy_writes.append((self._table, bytes(data)))


class FakeCursor:
    def __init__(self, db: FakeDatabase) -> None:
        self._db = db
        self._rows: list[tuple] = []

    def execute(self, sql: str, params=None) -> None:
        self._db.executed.append((sql, params))
        if "information_schema.tables" in sql:
            if params is None:
                self._rows = [(name,) for name in sorted(self._db.tables)]
            else:
                wanted = set(params[0])
                self._rows = [
                    (name,) for name in sorted(self._db.existing_tables) if name in wanted
                ]
        elif "pg_index" in sql:
            table = params[0].split(".")[-1].strip('"')
            self._rows = [(col,) for col in self._db.pk_columns.get(table, [])]
        elif "episode_meta,occurred_at" in sql:
            self._rows = [(self._db.null_occurred_at_count,)]
        elif sql.startswith("SELECT count(*) FROM"):
            table = _TABLE_RE.search(sql).group(1)
            self._rows = [(self._db.row_counts[table],)]
        else:
            self._rows = []

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def copy(self, sql: str):
        self._db.executed.append((sql, None))
        table = _TABLE_RE.search(sql).group(1)
        if "TO STDOUT" in sql:
            return FakeCopyOut(self._db.copy_data.get(table, []))
        return FakeCopyIn(self._db, table)


class FakeConnection:
    def __init__(self, db: FakeDatabase) -> None:
        self._db = db

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._db)

    def commit(self) -> None:
        self._db.committed = True

    def rollback(self) -> None:
        self._db.rolled_back = True

    def close(self) -> None:
        self._db.closed = True


class FakeDatabase:
    """Scripted catalog/data state shared by connection, cursor, and COPY fakes."""

    def __init__(
        self,
        *,
        tables: list[str] | None = None,
        pk_columns: dict[str, list[str]] | None = None,
        copy_data: dict[str, list[bytes]] | None = None,
        row_counts: dict[str, int] | None = None,
        null_occurred_at_count: int = 0,
        existing_tables: list[str] | None = None,
    ) -> None:
        self.tables = tables or []
        self.pk_columns = pk_columns or {}
        self.copy_data = copy_data or {}
        self.row_counts = row_counts or {}
        self.null_occurred_at_count = null_occurred_at_count
        self.existing_tables = existing_tables or []
        self.executed: list[tuple[str, object]] = []
        self.copy_writes: list[tuple[str, bytes]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def connection_factory(self, dsn: str) -> FakeConnection:
        self.connected_dsn = dsn
        return FakeConnection(self)


def refusing_connection_factory(dsn: str):
    raise AssertionError("connection_factory must not be called on this path")
