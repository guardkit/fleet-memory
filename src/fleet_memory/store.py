"""Store factory and namespace validation for fleet-memory.

Provides async context manager for AsyncPostgresStore with pgvector index configuration.
Namespace validation enforces underscores-only identifiers before database operations.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from langgraph.store.postgres.aio import AsyncPostgresStore, PoolConfig

from fleet_memory.embed import embed
from fleet_memory.errors import NamespaceValidationError

if TYPE_CHECKING:
    from fleet_memory.settings import Settings


# Namespace validation pattern: lowercase alphanumeric + underscores only
_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9_]+$")

# Slack added to pg_connect_timeout_s when bounding store-context entry:
# entry covers pool open plus store.setup(), so the bound must leave room
# for schema setup on a healthy connection while still failing fast when
# the database is unreachable (ASSUM-006).
_SETUP_SLACK_S = 5.0


def _dsn_target(dsn: str) -> str:
    """Render the database target from a DSN without credentials.

    Falls back to a generic label for non-URL conninfo strings so the
    caller never risks echoing a password.
    """
    parts = urlsplit(dsn)
    if not parts.hostname:
        return "configured database"
    target = parts.hostname
    if parts.port:
        target = f"{target}:{parts.port}"
    if parts.path and parts.path != "/":
        target = f"{target}{parts.path}"
    return target


def validate_namespace(namespace: tuple[str, ...]) -> None:
    """Validate namespace tuple enforces underscores-only identifiers.

    Args:
        namespace: Tuple of namespace identifiers (e.g., ("fleet_memory", "project", "chunk"))

    Raises:
        NamespaceValidationError: If any identifier contains hyphens or invalid characters

    Example:
        >>> validate_namespace(("fleet_memory", "my_project", "chunk"))  # OK
        >>> validate_namespace(("fleet_memory", "my-project", "chunk"))  # Raises
    """
    invalid_parts = []
    for part in namespace:
        if not part or not _NAMESPACE_PATTERN.match(part):
            invalid_parts.append(part)

    if invalid_parts:
        raise NamespaceValidationError(namespace=namespace, invalid_parts=invalid_parts)


@asynccontextmanager
async def async_store_context(
    settings: Settings,
    embed_fn: callable | None = None,
) -> AsyncIterator[AsyncPostgresStore]:
    """Create configured AsyncPostgresStore with pgvector index and pool lifecycle.

    Entry runs store.setup() to initialize schema. Exit closes connection pool cleanly.
    When embed_fn is None, constructs real httpx embed callable from settings.

    Args:
        settings: Configuration with pg_dsn, embed_dims, pool settings, timeout
        embed_fn: Optional embed callable for testing; if None, uses real httpx embed

    Yields:
        Configured AsyncPostgresStore with index config for semantic search

    Raises:
        Exception: Any database or connection errors (credentials stripped from messages)

    Example:
        >>> settings = Settings(...)
        >>> fake_embed = make_fake_embed(768)
        >>> async with async_store_context(settings, embed_fn=fake_embed) as store:
        ...     await store.put(("fleet_memory", "proj", "item"), "key", {"content": "..."})

    Implementation notes:
        - Driver: psycopg3 with psycopg-pool (plain postgresql:// conninfo, no +asyncpg)
        - Index config: {"dims": settings.embed_dims, "embed": callable, "fields": ["content"]}
        - Pool: min/max from settings.pg_pool_min/pg_pool_max
        - Timeout: settings.pg_connect_timeout_s (ASSUM-006 lever)
        - Verified against langgraph-checkpoint-postgres >=2.0 constructor signature
    """
    # Build embed callable: use provided fake or construct real one
    if embed_fn is None:
        # Real embed callable from settings (httpx-based)
        async def real_embed(texts: list[str]) -> list[list[float]]:
            return await embed(texts, settings)

        embed_callable = real_embed
    else:
        embed_callable = embed_fn

    # Configure index for pgvector semantic search
    # Verified contract: {dims: int, embed: callable, fields: list[str]}
    # Matches AsyncPostgresStore constructor signature in langgraph-checkpoint-postgres >=2.0
    index_config = {
        "dims": settings.embed_dims,
        "embed": embed_callable,
        "fields": ["content"],  # Index the "content" field in documents
    }

    # AsyncPostgresStore.from_conn_string returns an async context manager
    # Pool sizing: from settings.pg_pool_min and settings.pg_pool_max
    # Connection timeout: settings.pg_connect_timeout_s provides ASSUM-006 control lever
    #
    # Driver verification (langgraph-checkpoint-postgres >=2.0):
    # (a) Conninfo is plain postgresql:// psycopg3 format (verified in seam test)
    # (b) Index config shape {dims, embed, fields} matches constructor signature
    # (c) Pool min/max flow through from_conn_string pool_config parameter
    pool_config = PoolConfig(
        min_size=settings.pg_pool_min,
        max_size=settings.pg_pool_max,
        kwargs={"connect_timeout": settings.pg_connect_timeout_s},
    )

    # Bound context entry (pool open + setup) with asyncio.timeout: the
    # per-connection connect_timeout kwarg above does not bound the pool's
    # own open/wait retry loop (psycopg-pool retries failed connections for
    # its default 30s), so without this an unreachable database stalls
    # startup well past pg_connect_timeout_s (ASSUM-006).
    entry_timeout_s = settings.pg_connect_timeout_s + _SETUP_SLACK_S
    async with AsyncExitStack() as stack:
        try:
            async with asyncio.timeout(entry_timeout_s):
                store = await stack.enter_async_context(
                    AsyncPostgresStore.from_conn_string(
                        settings.pg_dsn,
                        index=index_config,
                        pool_config=pool_config,
                    )
                )
                # Initialize schema (creates tables/indexes if not exists)
                await store.setup()
        except TimeoutError as exc:
            # Credential hygiene: name the target host/port/db only - never
            # interpolate the DSN itself, which carries the password.
            raise TimeoutError(
                f"Timed out connecting to Postgres at {_dsn_target(settings.pg_dsn)} "
                f"after {entry_timeout_s}s "
                f"(pg_connect_timeout_s={settings.pg_connect_timeout_s})"
            ) from exc

        yield store
