"""Integration test fixtures for ephemeral PostgreSQL orchestration.

Self-contained fixture module that manages ephemeral PostgreSQL + pgvector instances
for integration tests. Each test session gets a unique Docker Compose project with:
- Random non-5432 port to avoid conflicts
- UUID-based project name for parallel worktree isolation
- Automatic cleanup on normal exit (request.addfinalizer) and aborted runs (atexit)
- Health check polling before yielding DSN

No imports from fleet_memory.settings - reads environment only.
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


def _get_random_port() -> int:
    """Allocate a random free port by binding to port 0 and reading assigned port.

    There's a small race condition window between releasing the socket and using
    the port, but docker compose will fail loudly on collision and can retry.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def _wait_for_pg_health(project_name: str, compose_file: Path, timeout: int = 30) -> bool:
    """Poll docker compose health check until healthy or timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                project_name,
                "ps",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json

            services = json.loads(result.stdout)
            if isinstance(services, dict):
                services = [services]
            for svc in services:
                if svc.get("Health") == "healthy":
                    return True
        time.sleep(0.5)
    return False


def _teardown_compose(project_name: str, compose_file: Path) -> None:
    """Idempotent teardown: stop and remove containers + volumes."""
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "-p",
            project_name,
            "down",
            "-v",
            "--remove-orphans",
        ],
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="session")
def ephemeral_pg(request: pytest.FixtureRequest) -> Generator[str, None, None]:
    """Session-scoped ephemeral PostgreSQL + pgvector instance.

    Yields a postgresql:// DSN on a random port. Automatically tears down
    containers and volumes after session completion or on aborted runs.

    Raises:
        RuntimeError: If Docker is unavailable or container fails to start
    """
    # Check Docker availability
    docker_check = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        check=False,
    )
    if docker_check.returncode != 0:
        pytest.skip(
            "Docker is not available. Integration tests require Docker or a compatible "
            "container runtime. Install Docker Desktop or configure your container runtime."
        )

    # Generate unique project name and port
    project_uid = uuid4().hex[:8]
    project_name = f"fleet_memory_test_{project_uid}"
    port = _get_random_port()

    # Locate docker-compose.yml
    # Assumes tests are in <repo>/tests/integration and compose is in <repo>/deploy/local
    repo_root = Path(__file__).parent.parent.parent
    compose_file = repo_root / "deploy" / "local" / "docker-compose.yml"

    if not compose_file.exists():
        raise RuntimeError(
            f"Docker Compose file not found at {compose_file}. "
            "Ensure deploy/local/docker-compose.yml exists."
        )

    # Set environment for compose
    env = os.environ.copy()
    env["PGPORT"] = str(port)

    # Start compose project
    start_result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "-p",
            project_name,
            "up",
            "-d",
            "--wait",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if start_result.returncode != 0:
        raise RuntimeError(f"Failed to start ephemeral PostgreSQL: {start_result.stderr}")

    # Wait for health check
    if not _wait_for_pg_health(project_name, compose_file, timeout=30):
        _teardown_compose(project_name, compose_file)
        raise RuntimeError(
            f"Ephemeral PostgreSQL did not become healthy within 30 seconds. "
            f"Project: {project_name}, Port: {port}"
        )

    # Build DSN
    dsn = f"postgresql://fleet_memory:fleet_memory@127.0.0.1:{port}/fleet_memory"

    # Register teardown handlers
    def teardown() -> None:
        _teardown_compose(project_name, compose_file)

    request.addfinalizer(teardown)
    atexit.register(teardown)

    yield dsn

    # Explicit teardown (also called by finalizer, but explicit for clarity)
    teardown()


@pytest.fixture(scope="session")
def ephemeral_pg_factory(
    request: pytest.FixtureRequest,
) -> Generator[Generator[str, None, None], None, None]:
    """Factory fixture to create multiple isolated ephemeral PostgreSQL instances.

    Useful for parallel isolation tests that need two distinct databases in the
    same test session.

    Yields a generator that produces DSNs. Each call to next() creates a new
    ephemeral instance with automatic cleanup.

    Usage:
        def test_isolation(ephemeral_pg_factory):
            dsn1 = next(ephemeral_pg_factory)
            dsn2 = next(ephemeral_pg_factory)
            # dsn1 and dsn2 are completely isolated
    """
    created_projects: list[tuple[str, Path]] = []

    def _factory() -> Generator[str, None, None]:
        """Generate a new ephemeral PostgreSQL instance."""
        # Check Docker availability
        docker_check = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
        )
        if docker_check.returncode != 0:
            pytest.skip("Docker is not available")

        project_uid = uuid4().hex[:8]
        project_name = f"fleet_memory_test_{project_uid}"
        port = _get_random_port()

        repo_root = Path(__file__).parent.parent.parent
        compose_file = repo_root / "deploy" / "local" / "docker-compose.yml"

        if not compose_file.exists():
            raise RuntimeError(f"Docker Compose file not found at {compose_file}")

        env = os.environ.copy()
        env["PGPORT"] = str(port)

        start_result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                project_name,
                "up",
                "-d",
                "--wait",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if start_result.returncode != 0:
            raise RuntimeError(f"Failed to start ephemeral PostgreSQL: {start_result.stderr}")

        if not _wait_for_pg_health(project_name, compose_file, timeout=30):
            _teardown_compose(project_name, compose_file)
            raise RuntimeError("Ephemeral PostgreSQL did not become healthy within 30 seconds")

        created_projects.append((project_name, compose_file))
        dsn = f"postgresql://fleet_memory:fleet_memory@127.0.0.1:{port}/fleet_memory"

        yield dsn

        # Teardown this instance
        _teardown_compose(project_name, compose_file)

    # Register global cleanup for all factory-created instances
    def cleanup_all() -> None:
        for project_name, compose_file in created_projects:
            _teardown_compose(project_name, compose_file)

    request.addfinalizer(cleanup_all)
    atexit.register(cleanup_all)

    yield _factory()

    # Final cleanup
    cleanup_all()
