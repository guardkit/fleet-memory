"""Root-level pytest fixtures for fleet_memory tests.

This conftest provides fixtures available to ALL test types (unit and integration).
The fake_embed fixture is defined here to ensure unit tests can use fake embeddings
without requiring database or network connections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def isolate_fence_state(tmp_path_factory, monkeypatch) -> None:
    """Keep every test out of the operator's real ``~/.local/state/fleet-memory``.

    Since the relay mints a liveness-fence progress marker in its lifespan, any test
    that enters that lifespan would otherwise write a real file into the operator's
    state directory — and a stale marker there is exactly what would make the
    installed fence believe a dead relay had just started. (This is not theoretical:
    running the suite once did it.) Autouse, so no future test has to remember.

    Tests that want a specific path still set one explicitly; this only moves the
    default out of harm's way.
    """
    state_dir = tmp_path_factory.mktemp("fence_state")
    monkeypatch.setenv("FLEET_MEMORY_FENCE_STATE_DIR", str(state_dir))
    monkeypatch.setenv(
        "FLEET_MEMORY_FENCE_RELAY_MARKER_PATH", str(state_dir / "relay-progress.json")
    )


@pytest.fixture
def fake_embed() -> Callable[[str], list[float]]:
    """Deterministic fake embedding function for unit tests.

    Returns a 768-dimensional vector (typical for many embedding models) with
    deterministic values based on input text hash. No imports from fleet_memory.embed
    required - this is a pure test fake that requires no database or network.

    Usage:
        def test_something(fake_embed):
            vector = fake_embed("test text")
            assert len(vector) == 768
            # Same input always produces same output
            assert fake_embed("test text") == vector
    """

    def _fake_embed(text: str) -> list[float]:
        """Generate deterministic 768-dim vector from text hash."""
        # Use hash of text to seed deterministic values
        seed = hash(text) & 0xFFFFFFFF  # Ensure 32-bit positive int

        # Generate 768 dimensions using a simple PRNG-like pattern
        # This is NOT cryptographically secure, just deterministic for tests
        vector = []
        current = seed
        for i in range(768):
            # Simple linear congruential generator for deterministic values
            current = (current * 1103515245 + 12345) & 0xFFFFFFFF
            # Normalize to [-1, 1] range typical for embeddings
            value = (current / 0xFFFFFFFF) * 2.0 - 1.0
            vector.append(value)

        return vector

    return _fake_embed
