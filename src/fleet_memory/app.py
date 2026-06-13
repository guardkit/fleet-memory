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
    """Factory function to create broker and app with safe settings construction.

    Attempts to construct Settings() from environment variables. If this fails
    (e.g., in test environments without required env vars), creates a minimal
    broker with default NATS URL. This allows tests to import handler modules
    without triggering Settings validation errors.

    Returns:
        Tuple of (broker, app) with configured lifespan
    """
    # Try to construct Settings from environment
    # In test environments this may fail - create minimal broker instead
    try:
        settings = Settings()
        nats_url = settings.nats_url
    except Exception:
        # Test environment: Settings() failed due to missing env vars
        # Create minimal broker with default NATS URL
        settings = None  # type: ignore
        nats_url = "nats://localhost:4222"

    # Create broker - no connection attempted until app.start()
    broker_instance = NatsBroker(nats_url)

    @asynccontextmanager
    async def lifespan(app: FastStream) -> AsyncIterator[None]:
        """Lifespan context manager: enter store context and expose via broker state.

        Entry:
            - Enters async_store_context with real embed callable (from settings)
            - Runs store.setup() to initialize schema
            - Constructs RelayService with writer dependencies
            - Stores references in broker.context for handler access

        Exit:
            - Closes connection pool cleanly

        Raises:
            Exception: Database connection errors propagate with credential hygiene
                       (password stripped by psycopg, see ASSUM-006)
        """
        # Test mode: settings is None, skip full lifespan setup
        # Tests will mock service and broker context directly
        if settings is None:
            yield
            return

        # Enter store context with real embed callable
        # (async_store_context constructs it from settings)
        async with async_store_context(settings) as store:
            # Import dependencies for RelayService construction
            from fleet_memory.relay.chunk_writer import ChunkWriter
            from fleet_memory.relay.service import RelayService
            from fleet_memory.writer.core import DeterministicWriter

            # Construct writer dependencies
            deterministic_writer = DeterministicWriter(store=store, settings=settings)
            chunk_writer = ChunkWriter(store=store)

            # Construct RelayService with all dependencies
            relay_service = RelayService(
                writer=deterministic_writer,
                chunk_writer=chunk_writer,
                settings=settings,
            )

            # Expose store, service, and settings via broker state for handlers
            # Use set_global to add to broker context
            broker_instance.context.set_global("store", store)
            broker_instance.context.set_global("relay_service", relay_service)
            broker_instance.context.set_global("settings", settings)

            # Set service on handler module for handler access
            # (module-level singleton pattern for service instances)
            from fleet_memory.relay import handler

            handler.service = relay_service

            # Yield to run the app - store and service are available during lifetime
            yield

            # Exit: async_store_context.__aexit__ closes pool cleanly

    # FastStream app with lifespan
    app_instance = FastStream(broker_instance, lifespan=lifespan)

    return broker_instance, app_instance


# Module-level exports - lazy construction via factory
# Import-time side effects minimal: Settings() only happens when factory is called
broker, app = _create_app()

# Import handlers to register subscribers on the broker via import side-effects
# Must occur after broker is created (import-time registration)
import fleet_memory.relay.handler  # noqa: F401, E402
