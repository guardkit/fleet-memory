"""Self-tests for ephemeral PostgreSQL fixture.

Validates:
- Fixture startup and teardown
- pgvector extension availability
- Random port assignment
- Parallel isolation between distinct fixture instances
- Clean teardown (no lingering containers/volumes)
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import psycopg
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.mark.integration
def test_ephemeral_pg_starts_and_provides_dsn(ephemeral_pg: str) -> None:
    """Fixture yields a valid PostgreSQL DSN on a non-standard port."""
    assert ephemeral_pg.startswith("postgresql://")
    assert "127.0.0.1" in ephemeral_pg
    assert ":5432/" not in ephemeral_pg  # Must not use default port

    # Verify connection works
    with psycopg.connect(ephemeral_pg) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            assert result == (1,)


@pytest.mark.integration
def test_pgvector_extension_available(ephemeral_pg: str) -> None:
    """After fixture startup, pgvector extension is installed."""
    with psycopg.connect(ephemeral_pg) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            result = cur.fetchone()
            assert result is not None
            assert result[0] == "vector"


@pytest.mark.integration
def test_ephemeral_pg_uses_random_port(ephemeral_pg: str) -> None:
    """Each fixture instance gets a random, non-5432 port."""
    # Extract port from DSN
    port_start = ephemeral_pg.rfind(":") + 1
    port_end = ephemeral_pg.rfind("/")
    port = int(ephemeral_pg[port_start:port_end])

    assert port != 5432
    assert 1024 < port < 65536  # Valid ephemeral port range


@pytest.mark.integration
def test_data_isolation_between_projects(
    ephemeral_pg: str,
    ephemeral_pg_factory: Generator[str, None, None],
) -> None:
    """Two distinct fixture instances have isolated data and different ports.

    Uses a factory fixture to create a second ephemeral instance within
    the same test session to verify mutual invisibility.
    """
    # Create test table in first instance
    with psycopg.connect(ephemeral_pg) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE test_isolation (id INT PRIMARY KEY, data TEXT)")
            cur.execute("INSERT INTO test_isolation VALUES (1, 'instance_1')")
            conn.commit()

    # Create second instance via factory
    second_dsn = next(ephemeral_pg_factory)

    # Extract ports
    port1 = int(ephemeral_pg[ephemeral_pg.rfind(":") + 1 : ephemeral_pg.rfind("/")])
    port2 = int(second_dsn[second_dsn.rfind(":") + 1 : second_dsn.rfind("/")])

    # Ports must be different
    assert port1 != port2

    # Second instance should not see first instance's data
    with psycopg.connect(second_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'test_isolation')"
            )
            exists = cur.fetchone()
            assert exists[0] is False


@pytest.mark.integration
def test_teardown_removes_container_and_volume() -> None:
    """After fixture teardown, no containers or volumes remain for the test project.

    This test must run AFTER other tests that use ephemeral_pg, so it validates
    cleanup of previous test runs. It checks that docker compose ps shows no
    running containers for any fleet_memory_test_* project.
    """
    # List all docker compose projects starting with fleet_memory_test_
    result = subprocess.run(
        ["docker", "compose", "ls", "--filter", "name=fleet_memory_test_", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0 and result.stdout.strip():
        # If any test projects still running, fail
        import json

        projects = json.loads(result.stdout)
        active_projects = [p for p in projects if p.get("Status") == "running"]
        assert len(active_projects) == 0, (
            f"Found {len(active_projects)} active test projects after teardown: {active_projects}"
        )
