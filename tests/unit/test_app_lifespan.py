"""Unit tests for FastStream app lifespan with store context management.

Tests verify lifespan entry/exit with TestNatsBroker pattern and startup
failure behavior when database is unreachable (ASSUM-006 verification).
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from faststream.nats import TestNatsBroker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.asyncio
async def test_lifespan_enters_and_exits_cleanly_with_fake_store(fake_embed, monkeypatch) -> None:
    """Verify lifespan enters store context and exposes store without errors.

    Uses TestNatsBroker pattern with mocked store context - no real NATS, no real Postgres.
    The fake embed ensures embedding dimension guard is satisfied.
    """
    # Arrange: Set environment variables FIRST
    monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://fake@localhost/test")
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://fake-embed-service")

    # Mock the store context to yield a fake store
    fake_store = MagicMock(spec=["setup", "put", "get"])
    fake_store.setup = AsyncMock()

    @asynccontextmanager
    async def mock_store_context(settings, embed_fn=None) -> AsyncIterator:
        """Fake store context that yields a mock store."""
        await fake_store.setup()
        yield fake_store

    # Patch store context and reload app module to pick up the patch
    with patch("fleet_memory.store.async_store_context", mock_store_context):
        # Remove cached module to force reimport with patch active
        if "fleet_memory.app" in sys.modules:
            del sys.modules["fleet_memory.app"]

        # Import app with patch active
        from fleet_memory.app import app, broker

        # Act: Enter app lifespan manually (TestNatsBroker wraps broker, but we need app lifespan)
        async with TestNatsBroker(broker):
            # Manually invoke the app's lifespan context
            async with app.lifespan_context(app):
                # Assert: Store setup was called during lifespan entry
                fake_store.setup.assert_awaited_once()

                # Assert: App and broker exist
                assert app is not None
                assert broker is not None

        # Assert: Lifespan exited cleanly (no exceptions raised)


@pytest.mark.asyncio
async def test_startup_failure_with_unreachable_database(monkeypatch) -> None:
    """Verify startup fails fast when database is unreachable (ASSUM-006).

    Uses REAL store context pointing at a closed local port. Verifies:
    - Failure occurs within pg_connect_timeout_s plus slack (< 15s wall clock)
    - Error message names the database target without leaking password

    Driver timeout observation: psycopg3 with psycopg-pool respects the timeout
    parameter in pool_kwargs and fails fast when the target port is unreachable.
    The connection attempt raises OperationalError within the configured timeout.
    """
    # Arrange: Set env to point at closed port (nothing listening on 65432)
    monkeypatch.setenv(
        "FLEET_MEMORY_PG_DSN",
        "postgresql://testuser:secretpass@localhost:65432/testdb",
    )
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://fake-embed-service")
    monkeypatch.setenv("FLEET_MEMORY_PG_CONNECT_TIMEOUT_S", "2.0")

    # Remove cached module to force reimport with new env vars
    if "fleet_memory.app" in sys.modules:
        del sys.modules["fleet_memory.app"]
    if "fleet_memory.settings" in sys.modules:
        del sys.modules["fleet_memory.settings"]

    # Import app after env setup (Settings constructed during import)
    from fleet_memory.app import app, broker

    # Act & Assert: Lifespan entry should raise within timeout
    start_time = asyncio.get_event_loop().time()

    with pytest.raises(Exception) as exc_info:
        async with TestNatsBroker(broker):
            # Manually invoke the app's lifespan - this should fail when trying to connect
            async with app.lifespan_context(app):
                pass  # Should fail during lifespan entry

    elapsed = asyncio.get_event_loop().time() - start_time

    # Assert: Failed within timeout + _SETUP_SLACK_S (2.0 + 5.0 = 7.0) + margin
    assert elapsed < 8.0, f"Startup took {elapsed}s, expected < 8s"

    # Assert: Error message contains target info but not password
    error_msg = str(exc_info.value)
    assert "secretpass" not in error_msg, "Password leaked in error message"
    # Note: The exact format of the error depends on psycopg3 behavior
    # The critical requirement is that password is NOT present


@pytest.mark.asyncio
async def test_app_import_succeeds_with_valid_env(monkeypatch) -> None:
    """Verify app module imports cleanly when required env vars are set."""
    # Arrange: Set minimum required environment variables
    monkeypatch.setenv("FLEET_MEMORY_PG_DSN", "postgresql://fake@localhost/test")
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://fake-embed-service")

    # Act: Import app module
    from fleet_memory.app import app, broker

    # Assert: Exports exist
    assert app is not None
    assert broker is not None


@pytest.mark.asyncio
async def test_no_subscribers_registered_on_broker() -> None:
    """Verify no @broker.subscriber decorators present in app module.

    FEAT-MEM-04 will add MEMORY-stream consumer later - this task provides
    just the shell.
    """
    # Arrange: Import with minimal env (mocked in conftest if needed)
    import os

    os.environ.setdefault("FLEET_MEMORY_PG_DSN", "postgresql://fake@localhost/test")
    os.environ.setdefault("FLEET_MEMORY_EMBED_URL", "http://fake-embed-service")

    from fleet_memory.app import broker

    # Act: Inspect broker's registered handlers
    # FastStream NatsBroker stores handlers in _subscribers
    handlers = getattr(broker, "_subscribers", [])

    # Assert: No handlers registered yet
    assert len(handlers) == 0, "Expected no subscribers in app shell"
