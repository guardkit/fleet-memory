"""Unit tests for fleet_memory.fixture.scratch (TASK-ABL5-004).

No Docker/Postgres: name construction/validation and SQL/pattern construction
are tested pure (LIKE semantics evaluated with a faithful pattern-to-regex
translation); the database side is an injected fake connection seam that
scripts rowcounts and records every statement. Live-store isolation proof
(sibling scratch + corpus survive a discard) is TASK-ABL5-006's integration
suite.
"""

from __future__ import annotations

import re

import pytest

from fleet_memory.fixture import FixtureError, ScratchNamespaceError
from fleet_memory.fixture.scratch import (
    DISCARD_STORE_SQL,
    DISCARD_VECTORS_SQL,
    LIST_PREFIXES_SQL,
    NAMESPACE_ROOT,
    SCRATCH_PREFIX,
    discard_patterns,
    discard_scratch,
    list_scratch_projects,
    scratch_namespace,
    scratch_project,
)
from tests.unit.fixture.fakes import refusing_connection_factory

PASSWORD = "S3cr3tPW"
DSN = f"postgresql://runner:{PASSWORD}@runhost:5544/perrun"


def like_to_regex(pattern: str, escape: str = "\\") -> re.Pattern[str]:
    """Translate a SQL LIKE pattern (with ESCAPE) to an anchored regex.

    Mirrors Postgres semantics: ``%`` any string, ``_`` any single character,
    ``<escape><char>`` a literal char.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == escape:
            i += 1
            out.append(re.escape(pattern[i]))
        elif char == "%":
            out.append(".*")
        elif char == "_":
            out.append(".")
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.DOTALL)


def matches_discard(prefix: str, rollout_id: str) -> bool:
    """Evaluate the discard match clause (exact OR LIKE) for one stored prefix."""
    exact, pattern = discard_patterns(rollout_id)
    return prefix == exact or like_to_regex(pattern).match(prefix) is not None


# ----- fake connection seam -----


class FakeScratchCursor:
    def __init__(self, db: FakeScratchDatabase) -> None:
        self._db = db
        self._rows: list[tuple] = []
        self.rowcount = -1

    def execute(self, sql: str, params=None) -> None:
        self._db.executed.append((sql, params))
        if self._db.fail_on and self._db.fail_on in sql:
            raise RuntimeError(f"query failed on {DSN} (password={PASSWORD})")
        if sql == DISCARD_VECTORS_SQL:
            self.rowcount = self._db.vector_rows
            self._db.vector_rows = 0  # consumed: models the rows being gone
        elif sql == DISCARD_STORE_SQL:
            self.rowcount = self._db.store_rows
            self._db.store_rows = 0
        elif sql == LIST_PREFIXES_SQL:
            self._rows = [(prefix,) for prefix in self._db.prefixes]

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class FakeScratchConnection:
    def __init__(self, db: FakeScratchDatabase) -> None:
        self._db = db

    def cursor(self) -> FakeScratchCursor:
        return FakeScratchCursor(self._db)

    def commit(self) -> None:
        self._db.committed = True

    def rollback(self) -> None:
        self._db.rolled_back = True

    def close(self) -> None:
        self._db.closed = True


class FakeScratchDatabase:
    """Scripted store state: matching rowcounts, distinct prefixes, failure hook."""

    def __init__(
        self,
        *,
        store_rows: int = 0,
        vector_rows: int = 0,
        prefixes: list[str] | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.store_rows = store_rows
        self.vector_rows = vector_rows
        self.prefixes = prefixes or []
        self.fail_on = fail_on
        self.executed: list[tuple[str, object]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def connection_factory(self, dsn: str) -> FakeScratchConnection:
        self.connected_dsn = dsn
        return FakeScratchConnection(self)


# ----- name construction + validation -----


def test_scratch_project_prefixes_rollout_id():
    assert scratch_project("run_01") == "scratch_run_01"
    assert SCRATCH_PREFIX == "scratch_"


def test_scratch_namespace_tuple_shape():
    assert scratch_namespace("run1", "chunk") == ("fleet_memory", "scratch_run1", "chunk")


@pytest.mark.seam
def test_scratch_namespace_passes_public_store_validator():
    # Read-only use of the store's PUBLIC validator: the tuple this module
    # names must be writable by the rollout's own store client unchanged.
    from fleet_memory.store import validate_namespace

    validate_namespace(("fleet_memory", scratch_project("run_01"), "chunk"))
    validate_namespace(scratch_namespace("run_01", "chunk"))


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        " ",
        "Run1",  # uppercase
        "run-1",  # hyphen
        "run.1",  # dot (namespace separator)
        "run/1",  # path char
        "../run1",  # traversal
        "run 1",  # space
        "run%1",  # LIKE wildcard
        "röllout",  # unicode
        None,
        42,
        ["run1"],
    ],
)
def test_invalid_rollout_ids_raise_never_sanitised(bad_id):
    with pytest.raises(ScratchNamespaceError):
        scratch_project(bad_id)
    with pytest.raises(ScratchNamespaceError):
        scratch_namespace(bad_id, "chunk")
    with pytest.raises(ScratchNamespaceError):
        discard_patterns(bad_id)


def test_invalid_payload_type_raises():
    with pytest.raises(ScratchNamespaceError):
        scratch_namespace("run1", "chunk-type")
    with pytest.raises(ScratchNamespaceError):
        scratch_namespace("run1", "")
    with pytest.raises(ScratchNamespaceError):
        scratch_namespace("run1", None)


def test_error_messages_are_credential_free():
    with pytest.raises(ScratchNamespaceError) as excinfo:
        scratch_project("Run-1")
    assert PASSWORD not in str(excinfo.value)
    assert DSN not in str(excinfo.value)


# ----- pattern construction -----


def test_discard_patterns_exact_and_dotted():
    exact, pattern = discard_patterns("run1")
    assert exact == "fleet_memory.scratch_run1"
    assert pattern.endswith(".%")
    # Every underscore in the literal part is escaped for LIKE.
    assert pattern == "fleet\\_memory.scratch\\_run1.%"


def test_discard_patterns_escape_every_underscore():
    exact, pattern = discard_patterns("run_1")
    assert pattern.count("\\_") == exact.count("_") == 3


def test_discard_matches_only_the_exact_scratch_project():
    # Own rows: bare project prefix and any dotted payload namespace.
    assert matches_discard("fleet_memory.scratch_run1", "run1")
    assert matches_discard("fleet_memory.scratch_run1.chunk", "run1")
    assert matches_discard("fleet_memory.scratch_run1.build_outcome", "run1")
    assert matches_discard("fleet_memory.scratch_run1.a.b", "run1")

    # Corpus safety invariant: corpus projects and sibling scratch projects
    # never match run1's discard.
    assert not matches_discard("fleet_memory.guardkit.chunk", "run1")
    assert not matches_discard("fleet_memory.scratch_run2.chunk", "run1")
    assert not matches_discard("fleet_memory.scratch_run12.chunk", "run1")
    assert not matches_discard("fleet_memory.scratch_run1x.chunk", "run1")


def test_underscore_cannot_act_as_like_wildcard():
    # If '_' wildcarded, these single-character variants would match.
    assert not matches_discard("fleetXmemory.scratch_run1.chunk", "run1")
    assert not matches_discard("fleet_memory.scratchXrun1.chunk", "run1")
    assert not matches_discard("fleet_memory.scratch_runX1.chunk", "run_1")
    # And the properly-underscored sibling axis still works.
    assert matches_discard("fleet_memory.scratch_run_1.chunk", "run_1")
    assert not matches_discard("fleet_memory.scratch_run_12.chunk", "run_1")


# ----- SQL construction -----


def test_discard_sql_is_parameterised_with_pinned_escape():
    for sql in (DISCARD_VECTORS_SQL, DISCARD_STORE_SQL):
        assert "%(prefix)s" in sql
        assert "%(pattern)s" in sql
        assert "ESCAPE '\\'" in sql
    assert '"public"."store_vectors"' in DISCARD_VECTORS_SQL
    assert '"public"."store"' in DISCARD_STORE_SQL


def test_no_sql_references_created_at():
    for sql in (DISCARD_VECTORS_SQL, DISCARD_STORE_SQL, LIST_PREFIXES_SQL):
        assert "created_at" not in sql


# ----- discard behaviour via the fake seam -----


def test_discard_deletes_vectors_then_store_and_commits():
    db = FakeScratchDatabase(store_rows=7, vector_rows=7)
    deleted = discard_scratch(DSN, "run1", connection_factory=db.connection_factory)

    assert deleted == 7  # store rows deleted
    statements = [sql for sql, _ in db.executed]
    assert statements.index(DISCARD_VECTORS_SQL) < statements.index(DISCARD_STORE_SQL)
    assert db.committed
    assert not db.rolled_back
    assert db.closed


def test_discard_params_never_interpolated_into_sql():
    db = FakeScratchDatabase(store_rows=1, vector_rows=1)
    discard_scratch(DSN, "run1", connection_factory=db.connection_factory)
    exact, pattern = discard_patterns("run1")
    for sql, params in db.executed:
        assert "run1" not in sql  # the id never appears in SQL text
        assert params == {"prefix": exact, "pattern": pattern}


def test_discard_is_idempotent_second_call_returns_zero():
    db = FakeScratchDatabase(store_rows=5, vector_rows=5)
    assert discard_scratch(DSN, "run1", connection_factory=db.connection_factory) == 5
    assert discard_scratch(DSN, "run1", connection_factory=db.connection_factory) == 0


def test_invalid_rollout_id_never_touches_the_store():
    with pytest.raises(ScratchNamespaceError):
        discard_scratch(DSN, "Run-1", connection_factory=refusing_connection_factory)
    with pytest.raises(ScratchNamespaceError):
        discard_scratch(DSN, "", connection_factory=refusing_connection_factory)


# ----- list_scratch_projects -----


def test_list_scratch_projects_filters_root_and_prefix_and_sorts():
    db = FakeScratchDatabase(
        prefixes=[
            "fleet_memory.guardkit.chunk",  # corpus project: ignored
            "fleet_memory.scratch_run2.chunk",
            "fleet_memory.scratch_run1.chunk",
            "fleet_memory.scratch_run1.build_outcome",  # duplicate project
            "fleet_memory.scratch_run3",  # bare 2-segment prefix
            "other_root.scratch_x.chunk",  # foreign root: ignored
            "fleet_memory",  # 1-segment prefix: ignored
        ]
    )
    projects = list_scratch_projects(DSN, connection_factory=db.connection_factory)
    assert projects == ["scratch_run1", "scratch_run2", "scratch_run3"]
    assert all(p.startswith(SCRATCH_PREFIX) for p in projects)
    statements = [sql for sql, _ in db.executed]
    assert statements == [LIST_PREFIXES_SQL]
    assert not db.committed  # read-only
    assert db.closed


def test_list_scratch_projects_empty_store():
    db = FakeScratchDatabase(prefixes=[])
    assert list_scratch_projects(DSN, connection_factory=db.connection_factory) == []


# ----- credential hygiene -----


def test_connect_failure_never_leaks_password():
    def failing_factory(dsn: str):
        raise RuntimeError(f"could not connect using {dsn} (password={PASSWORD})")

    for call in (
        lambda: discard_scratch(DSN, "run1", connection_factory=failing_factory),
        lambda: list_scratch_projects(DSN, connection_factory=failing_factory),
    ):
        with pytest.raises(FixtureError) as excinfo:
            call()
        message = str(excinfo.value)
        assert PASSWORD not in message
        assert DSN not in message
        assert "runhost:5544/perrun" in message


def test_query_failure_is_scrubbed_not_committed_and_closed():
    db = FakeScratchDatabase(store_rows=1, vector_rows=1, fail_on="DELETE")
    with pytest.raises(FixtureError) as excinfo:
        discard_scratch(DSN, "run1", connection_factory=db.connection_factory)
    message = str(excinfo.value)
    assert PASSWORD not in message
    assert DSN not in message
    assert "runhost:5544/perrun" in message
    assert not db.committed
    assert db.closed


def test_namespace_root_matches_store_convention():
    assert NAMESPACE_ROOT == "fleet_memory"
