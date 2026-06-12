"""Integration tests for PostgreSQL connection pool lifecycle and pressure.

Validates:
- Pool lifecycle: clean connection cleanup after context exit
- Idempotent setup
- Connection timeout behavior (ASSUM-006)
- Pool pressure under concurrent load (ASSUM-004)

Requirements:
- Docker running for ephemeral_pg fixture
- Run with: pytest -m integration tests/integration/test_pool_lifecycle.py
"""

from __future__ import annotations

import asyncio

import psycopg
import pytest


@pytest.mark.integration
async def test_pool_lifecycle_no_connection_leak(test_settings, ephemeral_pg: str) -> None:
    """Pool lifecycle: enter → aput → exit leaks no connection.

    AC-005 (part 1): Verify pg_stat_activity connection count is restored after context exit.
    """
    from fleet_memory.embed import make_fake_embed
    from fleet_memory.store import async_store_context

    # Get baseline connection count
    def get_connection_count() -> int:
        """Count active connections to the test database."""
        with psycopg.connect(ephemeral_pg) as conn:
            with conn.cursor() as cur:
                # Extract database name from DSN
                db_name = ephemeral_pg.split("/")[-1]
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                    (db_name,),
                )
                result = cur.fetchone()
                return result[0] if result else 0

    baseline_count = get_connection_count()

    # Enter store context, perform operations, then exit
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    namespace = ("fleet_memory", "leak_test", "memory")

    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        # Perform some operations to ensure pool is actively used
        await store.aput(namespace, "test_key_1", {"content": "Test data 1"})
        await store.aget(namespace, "test_key_1")
        await store.aput(namespace, "test_key_2", {"content": "Test data 2"})

        # Connection count should be higher inside context
        inside_count = get_connection_count()
        assert inside_count > baseline_count, (
            "Connection count should increase while store context is active"
        )

    # After context exit, wait briefly for cleanup
    await asyncio.sleep(0.5)

    # Verify connection count restored
    after_count = get_connection_count()
    assert after_count == baseline_count, (
        f"Connection count should return to baseline after context exit. "
        f"Baseline: {baseline_count}, After: {after_count}, Inside: {inside_count}"
    )


@pytest.mark.integration
async def test_store_setup_is_idempotent(test_settings) -> None:
    """store.setup() run twice is idempotent - no errors on second call.

    AC-005 (part 2): Verify setup can be called multiple times safely.
    """
    from fleet_memory.embed import make_fake_embed
    from fleet_memory.store import async_store_context

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)

    # First context: setup() called implicitly in __aenter__
    async with async_store_context(test_settings, embed_fn=fake_embed) as store1:
        namespace = ("fleet_memory", "idempotent_test", "memory")
        await store1.aput(namespace, "key1", {"content": "First setup"})

    # Second context: setup() called again (should be idempotent)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store2:
        # Verify we can still operate normally
        await store2.aput(namespace, "key2", {"content": "Second setup"})

        # Verify previous data still exists (schema wasn't dropped)
        retrieved = await store2.aget(namespace, "key1")
        assert retrieved is not None, "Data from first setup should persist"
        assert retrieved.value["content"] == "First setup"


@pytest.mark.integration
async def test_connection_timeout_behavior(ephemeral_pg: str) -> None:
    """ASSUM-006: Verify connection timeout behavior against closed port.

    Tests pg_connect_timeout_s setting by attempting connection to a closed port.
    Records actual observed timeout behavior in test output.

    ASSUM-006 VERIFICATION:
    - Individual connection attempts timeout at connect_timeout (2s per attempt)
    - psycopg-pool alone would retry failed connections within its own timeout
      (default 30s) - connect_timeout is per-attempt, not a circuit breaker
    - async_store_context therefore bounds context entry (pool open + setup)
      with asyncio.timeout(pg_connect_timeout_s + 5s slack) and raises
      TimeoutError naming the target host/port without credentials
    - Total failure time = pg_connect_timeout_s + 5s slack, not the pool's 30s
    """
    from fleet_memory.embed import make_fake_embed
    from fleet_memory.settings import Settings
    from fleet_memory.store import async_store_context

    # Create settings with invalid port to force timeout
    # Use a port that's unlikely to have a service listening
    bad_dsn = "postgresql://fleet_memory:fleet_memory@127.0.0.1:9999/fleet_memory"
    timeout_s = 2.0  # Short timeout for test speed

    settings = Settings(
        pg_dsn=bad_dsn,
        embed_url="http://localhost:9000",
        embed_dims=768,
        pg_connect_timeout_s=timeout_s,
    )

    fake_embed = make_fake_embed(dims=settings.embed_dims)

    # Attempt to create store context - should timeout
    import time

    start_time = time.time()

    with pytest.raises(Exception) as exc_info:
        async with async_store_context(settings, embed_fn=fake_embed) as store:
            await store.aput(("test",), "key", {"content": "should not reach here"})

    elapsed = time.time() - start_time

    # ASSUM-006 observation recorded here:
    # connect_timeout controls INDIVIDUAL connection attempts (2s each); the
    # underlying psycopg-pool would keep retrying until its own 30s default
    # timeout. async_store_context bounds context entry with
    # asyncio.timeout(pg_connect_timeout_s + 5s slack), so entry fails fast
    # at ~7s here (2s + 5s) instead of the pool's 30s.
    entry_bound_s = timeout_s + 5.0
    assert elapsed < entry_bound_s + 3.0, (
        f"Store context entry should fail within pg_connect_timeout_s + 5s slack "
        f"(~{entry_bound_s}s). Actual: {elapsed:.2f}s."
    )

    # Verify exception type and credential hygiene: async_store_context raises
    # TimeoutError naming the target host/port, never the password
    assert isinstance(exc_info.value, TimeoutError), (
        f"Expected TimeoutError from bounded store-context entry, "
        f"got: {type(exc_info.value).__name__}"
    )
    error_msg = str(exc_info.value)
    assert "127.0.0.1:9999" in error_msg, (
        f"Error should name the database target, got: {error_msg}"
    )
    assert "fleet_memory:fleet_memory@" not in error_msg, "Credentials leaked in error"


@pytest.mark.integration
async def test_pool_pressure_concurrent_operations(test_settings) -> None:
    """Pool pressure (ASSUM-004): 15 concurrent aput against pg_pool_max=10.

    AC-006: Verify that operations beyond pool capacity queue and complete,
    rather than raising immediate errors. Records actual psycopg-pool behavior.
    """
    from fleet_memory.embed import make_fake_embed
    from fleet_memory.store import async_store_context

    # Override settings to have smaller pool for testing
    test_settings.pg_pool_max = 10
    test_settings.pg_pool_min = 2

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    namespace = ("fleet_memory", "pressure_test", "memory")

    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        # Launch 15 concurrent aput operations (exceeds pool_max of 10)
        async def put_operation(idx: int) -> dict:
            """Perform a single put operation and return result."""
            key = f"pressure_key_{idx}"
            content = {"content": f"Pressure test item {idx}", "index": idx}
            await store.aput(namespace, key, content)
            return {"index": idx, "success": True}

        # Run all operations concurrently
        import time

        start_time = time.time()

        try:
            results = await asyncio.gather(
                *[put_operation(i) for i in range(15)],
                return_exceptions=True,
            )
        except Exception as e:
            pytest.fail(f"Pool pressure test raised exception: {e}")

        elapsed = time.time() - start_time

        # ASSUM-004 verification:
        # Expected behavior: operations queue when pool is full, all complete successfully
        # Verify all operations completed
        successful = [r for r in results if isinstance(r, dict) and r.get("success")]
        failed = [r for r in results if isinstance(r, Exception)]

        # If actual behavior differs (pool raises errors instead of queueing),
        # this assertion will fail and flag the need to update ASSUM-004
        assert len(successful) == 15, (
            f"Expected all 15 operations to queue and complete. "
            f"Successful: {len(successful)}, Failed: {len(failed)}. "
            f"If operations timeout or fail, ASSUM-004 needs revision."
        )

        # All should complete within reasonable time (30s bound from AC-006)
        assert elapsed < 30.0, (
            f"All operations should complete within 30s. Actual: {elapsed:.2f}s"
        )

        # Verify all data was actually stored
        for i in range(15):
            key = f"pressure_key_{i}"
            retrieved = await store.aget(namespace, key)
            assert retrieved is not None, f"Item {i} should be stored despite pool pressure"
            assert retrieved.value["index"] == i


@pytest.mark.integration
async def test_pool_concurrent_reads_and_writes(test_settings) -> None:
    """Verify pool handles mixed concurrent read/write operations correctly."""
    from fleet_memory.embed import make_fake_embed
    from fleet_memory.store import async_store_context

    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    namespace = ("fleet_memory", "mixed_ops_test", "memory")

    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        # Pre-populate some data
        for i in range(5):
            await store.aput(namespace, f"existing_{i}", {"content": f"Existing {i}"})

        # Define mixed read/write operations
        async def write_op(idx: int) -> str:
            await store.aput(namespace, f"new_{idx}", {"content": f"New {idx}"})
            return f"write_{idx}"

        async def read_op(idx: int) -> str:
            result = await store.aget(namespace, f"existing_{idx % 5}")
            assert result is not None
            return f"read_{idx}"

        # Run 20 mixed operations (10 reads, 10 writes)
        operations = []
        for i in range(10):
            operations.append(write_op(i))
            operations.append(read_op(i))

        results = await asyncio.gather(*operations, return_exceptions=True)

        # Verify all operations completed without errors
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Mixed operations should complete without errors. Errors: {errors}"
        assert len(results) == 20, "All 20 operations should complete"
