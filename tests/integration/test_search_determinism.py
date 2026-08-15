"""Integration tests: identical query on identical data must give identical results.

Defect under test (2026-08-15 lane): the same search, run repeatedly against an
unchanged store over one warm connection, changes its answer part-way through.

Mechanism, proven in the ephemeral store:

1. ``AsyncPostgresStore.from_conn_string`` opens every pooled connection with
   ``prepare_threshold=0``, so the vector-search statement becomes a server-side
   prepared statement on its first execution. PostgreSQL plans a prepared
   statement with the real parameter values for its first five executions and
   then switches to a GENERIC plan. Under the generic plan the selectivity of
   ``store.prefix LIKE $2`` is unknown, the cost model flips, and the query
   changes scan path: approximate HNSW index scan below the flip, exact
   sequential scan above it. The two paths return different rows.

2. The approximate path is capped at ``hnsw.ef_search`` (default 40) candidate
   vectors before the namespace filter is applied, so it can also return fewer
   rows than were asked for.

The cure lives in ``fleet_memory.store.async_store_context``, in the pool's
connection kwargs: ``prepare_threshold=None`` plus
``-c plan_cache_mode=force_custom_plan`` pins the plan, and
``-c hnsw.iterative_scan=strict_order`` stops the approximate scan coming back
short. Neither touches ranking policy: ``hnsw.ef_search`` is deliberately left
at its default.

RESIDUAL, ledgered not cured: with an HNSW index present the approximate and
exact scan paths still rank differently, and a plain ``REINDEX`` of the index
(no data change at all) moves the answer -- measured 12/25 overlap before vs
after. Removing that hazard means dropping the approximate index, which is an
attended operator act and a call for Rich, not for this lane.

These tests are marker-gated and need Docker (``pytest -m integration``).
"""

from __future__ import annotations

import hashlib
import random

import psycopg
import pytest

# Enough rows that the planner will consider the approximate index at all: below
# roughly a thousand rows PostgreSQL sequential-scans regardless and the defect
# cannot appear.
SEED_ROWS = 4000
PROJECT = "guardkit"
QUERY = "subagent autobuild_runner autobuild outcome"
# Depth chosen to sit above the point where the expanded candidate ask
# (2 * limit + 1) exceeds hnsw.ef_search, which is where the two plans diverge.
DEPTH = 25
REPEATS = 20


def _unit_vector(text: str, dims: int) -> list[float]:
    """Deterministic, network-free, full-rank unit vector for ``text``."""
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    raw = [rng.gauss(0.0, 1.0) for _ in range(dims)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


def _embed_fn(dims: int):
    async def _embed(texts: list[str]) -> list[list[float]]:
        return [_unit_vector(t, dims) for t in texts]

    return _embed


def _bulk_seed(dsn: str, dims: int, rows: int) -> None:
    """Seed store + store_vectors directly.

    Bulk SQL rather than ``store.aput`` per row: the defect needs thousands of
    rows and per-row puts would take minutes. The vectors are produced by the
    same function the store's embed callable uses, so store and query agree.
    """
    types = ("build_outcome", "chunk", "document", "adr")
    store_rows = []
    vector_rows = []
    for i in range(rows):
        ptype = types[i % len(types)]
        key = f"{ptype}:{PROJECT}:ITEM_{i:05d}"
        prefix = f"fleet_memory.{PROJECT}.{ptype}"
        content = f"{ptype} record {i} for project {PROJECT}"
        store_rows.append((prefix, key, f'{{"natural_key": "{key}", "content": "{content}"}}'))
        vector_rows.append((prefix, key, "content", str(_unit_vector(content, dims))))

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM store WHERE prefix LIKE %s", (f"fleet_memory.{PROJECT}%",)
            )
            if cur.fetchone()[0] >= rows:
                return  # ephemeral_pg is session-scoped; seed once
            with cur.copy("COPY store (prefix, key, value) FROM STDIN") as copy:
                for row in store_rows:
                    copy.write_row(row)
            with cur.copy(
                "COPY store_vectors (prefix, key, field_name, embedding) FROM STDIN"
            ) as copy:
                for row in vector_rows:
                    copy.write_row(row)
            cur.execute("ANALYZE store")
            cur.execute("ANALYZE store_vectors")


@pytest.fixture
async def seeded_store(test_settings):
    """A store whose corpus is large enough to cross the approximate-index threshold."""
    from fleet_memory.store import async_store_context

    dims = test_settings.embed_dims
    embed_fn = _embed_fn(dims)

    # First entry creates the schema (and, on main, the HNSW index).
    async with async_store_context(test_settings, embed_fn=embed_fn):
        pass

    _bulk_seed(test_settings.pg_dsn, dims, SEED_ROWS)

    async with async_store_context(test_settings, embed_fn=embed_fn) as store:
        yield store


@pytest.mark.integration
async def test_repeated_identical_search_returns_identical_results(seeded_store) -> None:
    """Same query, same store, one warm pool: every answer must be byte-identical.

    FAILS on main -- the answer changes on the sixth execution, when PostgreSQL
    swaps the prepared statement's custom plan for a generic one and the query
    changes scan path.
    """
    store = seeded_store
    answers = []
    for _ in range(REPEATS):
        results = await store.asearch(("fleet_memory", PROJECT), query=QUERY, limit=DEPTH)
        answers.append([(item.key, item.score) for item in results])

    first = answers[0]
    diverged = [i for i, a in enumerate(answers, start=1) if a != first]
    assert not diverged, (
        f"Identical search returned a different answer on execution(s) {diverged} "
        f"of {REPEATS}: the first answer had {len(first)} rows, "
        f"execution {diverged[0]} had {len(answers[diverged[0] - 1])}. "
        "The store must not depend on how warm the connection is."
    )


@pytest.mark.integration
async def test_search_returns_the_full_depth_asked_for(seeded_store) -> None:
    """The store must return as many rows as were asked for when the corpus has them.

    FAILS on main above the approximate-index threshold: the HNSW scan yields at
    most ``hnsw.ef_search`` candidates before the namespace filter, so the answer
    silently comes back short.
    """
    store = seeded_store
    for depth in (10, 25, 26, 50, 100):
        results = await store.asearch(("fleet_memory", PROJECT), query=QUERY, limit=depth)
        assert len(results) == depth, (
            f"Asked for {depth} rows from a {SEED_ROWS}-row project, got {len(results)}"
        )


@pytest.mark.integration
async def test_adjacent_depths_agree_on_their_common_prefix(seeded_store) -> None:
    """Asking for one more row must not change the rows already being returned.

    FAILS on main when the two depths land on opposite sides of the planner's
    approximate/exact crossover: the answers are then drawn from different
    candidate sets rather than being prefixes of one ranking.
    """
    store = seeded_store
    shallow = await store.asearch(("fleet_memory", PROJECT), query=QUERY, limit=25)
    deep = await store.asearch(("fleet_memory", PROJECT), query=QUERY, limit=26)

    shallow_keys = [item.key for item in shallow]
    deep_keys = [item.key for item in deep]
    assert shallow_keys == deep_keys[: len(shallow_keys)], (
        "The top-25 of a depth-26 search is not the same as a depth-25 search; "
        "the two depths are being answered by different scan paths."
    )
