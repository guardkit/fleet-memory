"""The fence's store reader, against a REAL langgraph schema (marker-gated).

Unit tests prove the fence's judgement; this file proves the one thing they cannot —
that the SQL is right about the actual table the live store uses. It runs against an
ephemeral Postgres started by the integration fixtures, never against the live store,
never against :8005, and never near NATS.

Four properties:

1. Row age is measured correctly on a real schema.
2. Per-project filtering really does bound itself to ``fleet_memory.<project>``.
3. An empty store is detected as empty.
4. The reader's session is genuinely read-only — a watchdog must not be able to
   change what it watches, and that guarantee should be structural rather than a
   promise in a docstring.

Run: ``uv run --no-sync pytest -m integration tests/integration/test_fence_store_age.py``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fleet_memory.fence.store_age import (
    READ_ONLY_SESSION_SQL,
    project_patterns,
    read_store_facts,
)


def _project() -> str:
    """A fresh, namespace-legal project segment (^[a-z0-9_]+$)."""
    return f"fencetest_{uuid4().hex[:8]}"


async def _write_rows(store, project: str, count: int) -> None:
    namespace = ("fleet_memory", project, "memory")
    for i in range(count):
        await store.aput(
            namespace,
            f"entry_{i}",
            {"content": f"A remembered thing number {i}", "metadata": {"source": "fence_test"}},
        )


@pytest.mark.integration
async def test_the_newest_row_is_found_and_is_freshly_written(store_context, test_settings) -> None:
    """Just-written rows must read back as seconds old, not days."""
    store, _ = store_context
    project = _project()
    await _write_rows(store, project, 3)

    facts = read_store_facts(test_settings.pg_dsn, [project])

    assert facts.reachable is True
    assert facts.row_count >= 3
    assert facts.newest_updated_at is not None
    age = datetime.now(UTC) - facts.newest_updated_at
    assert age < timedelta(minutes=5)
    # updated_at is never behind created_at — the reason the fence reads it.
    assert facts.newest_updated_at >= facts.newest_created_at


@pytest.mark.integration
async def test_per_project_filtering_sees_only_that_project(store_context, test_settings) -> None:
    """The whole store looking healthy must not be able to hide one dark project."""
    store, _ = store_context
    mine = _project()
    theirs = _project()
    await _write_rows(store, mine, 4)
    await _write_rows(store, theirs, 7)

    facts = read_store_facts(test_settings.pg_dsn, [mine, theirs])
    by_name = {p.project: p for p in facts.per_project}

    assert by_name[mine].row_count == 4
    assert by_name[theirs].row_count == 7
    assert facts.row_count >= 11  # the whole store holds both, and possibly more


@pytest.mark.integration
async def test_a_project_with_nothing_stored_reads_as_empty(store_context, test_settings) -> None:
    store, _ = store_context
    await _write_rows(store, _project(), 2)  # something exists, just not for this name

    facts = read_store_facts(test_settings.pg_dsn, ["never_written_to"])

    assert facts.per_project[0].row_count == 0
    assert facts.per_project[0].newest_updated_at is None


@pytest.mark.integration
async def test_an_underscore_in_a_project_name_is_not_a_wildcard(
    store_context, test_settings
) -> None:
    """``_`` is a single-character LIKE wildcard; escaping it is what stops one
    project's check silently measuring a sibling's rows."""
    store, _ = store_context
    base = f"fenceesc_{uuid4().hex[:6]}"
    sibling = base.replace("_", "x", 1)  # differs only where the underscore was
    await _write_rows(store, base, 3)
    await _write_rows(store, sibling, 5)

    facts = read_store_facts(test_settings.pg_dsn, [base])
    assert facts.per_project[0].row_count == 3  # not 8


@pytest.mark.integration
async def test_an_empty_store_is_detected_as_empty(ephemeral_pg_factory) -> None:
    """A separate, untouched database: the schema exists, nothing is in it."""
    from fleet_memory.embed import make_fake_embed
    from fleet_memory.settings import Settings
    from fleet_memory.store import async_store_context

    dsn = next(ephemeral_pg_factory)
    settings = Settings(pg_dsn=dsn, embed_url="http://unused-by-fence", embed_dims=768)
    async with async_store_context(settings, embed_fn=make_fake_embed(dims=768)):
        pass  # entering the context runs setup(), creating the real schema

    facts = read_store_facts(dsn)

    assert facts.reachable is True
    assert facts.row_count == 0
    assert facts.newest_updated_at is None


@pytest.mark.integration
async def test_the_readers_session_really_is_read_only(store_context, test_settings) -> None:
    """Prove the guarantee against a real server, not just by reading the constant.

    This test earned its keep: the first version of READ_ONLY_SESSION_SQL set only
    ``default_transaction_read_only``, which binds transactions started *afterwards* —
    and psycopg had already opened one, so an INSERT went straight through. Setting
    the current transaction read-only first is what actually closes it.
    """
    import psycopg

    store, _ = store_context
    project = _project()
    await _write_rows(store, project, 1)

    conn = psycopg.connect(test_settings.pg_dsn)
    try:
        cur = conn.cursor()
        for statement in READ_ONLY_SESSION_SQL:
            cur.execute(statement)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            cur.execute(
                'INSERT INTO "public"."store" (prefix, key, value) '
                "VALUES ('fleet_memory.should_not_exist', 'k', '{}'::jsonb)"
            )
    finally:
        conn.close()

    # And the row really was not written.
    facts = read_store_facts(test_settings.pg_dsn, ["should_not_exist"])
    assert facts.per_project[0].row_count == 0


@pytest.mark.integration
async def test_the_prefix_patterns_match_what_the_writer_actually_persists(
    store_context, test_settings
) -> None:
    """Namespaces persist as dot-joined text; the fence must build the same string."""
    import psycopg

    store, _ = store_context
    project = _project()
    await _write_rows(store, project, 1)
    exact, pattern = project_patterns(project)

    conn = psycopg.connect(test_settings.pg_dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT DISTINCT prefix FROM "public"."store" WHERE prefix LIKE %(pattern)s '
            "ESCAPE '\\'",
            {"pattern": pattern},
        )
        prefixes = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    assert prefixes == [f"{exact}.memory"]
