"""FastStream app shell with lifespan-managed AsyncPostgresStore.

Minimal app per nats-asyncio-service template: module-level broker,
FastStream app with lifespan that enters async_store_context and exposes
the store for future handlers. No subscribers yet - FEAT-MEM-04 adds the
MEMORY-stream consumer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from faststream import FastStream
from faststream.nats import NatsBroker

from fleet_memory.settings import Settings
from fleet_memory.store import async_store_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _create_app() -> tuple[NatsBroker, FastStream]:
    """Factory function to create broker and app with deferred settings construction.

    Settings are constructed here (not at module import time) to allow tests to
    set environment variables before Settings validation runs.

    Returns:
        Tuple of (broker, app) with configured lifespan
    """
    # Settings constructed inside factory - tests can set env vars before calling this
    settings = Settings()

    # Create broker - no connection attempted until app.start()
    broker_instance = NatsBroker(settings.nats_url)

    @asynccontextmanager
    async def lifespan(app: FastStream) -> AsyncIterator[None]:
        """Lifespan context manager: enter store context and expose via broker state.

        Entry:
            - Enters async_store_context with real embed callable (from settings)
            - Runs store.setup() to initialize schema
            - Stores reference in broker.context for handler access

        Exit:
            - Closes connection pool cleanly

        Raises:
            Exception: Database connection errors propagate with credential hygiene
                       (password stripped by psycopg, see ASSUM-006)
        """
        # Enter store context with real embed callable
        # (async_store_context constructs it from settings)
        async with async_store_context(settings) as store:
            # Expose store via broker state for future handlers
            # Use set_global to add to broker context
            broker_instance.context.set_global("store", store)

            # Yield to run the app - store is available during service lifetime
            yield

            # Exit: async_store_context.__aexit__ closes pool cleanly

    # FastStream app with lifespan
    # No subscribers registered yet - FEAT-MEM-04 adds MEMORY-stream consumer
    app_instance = FastStream(broker_instance, lifespan=lifespan)

    return broker_instance, app_instance


# Module-level exports - lazy construction via factory
# Import-time side effects minimal: Settings() only happens when factory is called
broker, app = _create_app()
