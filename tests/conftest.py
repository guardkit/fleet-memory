"""Root-level pytest fixtures for fleet_memory tests.

This conftest provides fixtures available to ALL test types (unit and integration).
The fake_embed fixture is defined here to ensure unit tests can use fake embeddings
without requiring database or network connections.
"""

from __future__ import annotations

import sys
import pathlib

# Ensure the project's src directory is on the import path for all tests.
root = pathlib.Path(__file__).resolve().parents[1]
src_path = root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


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
