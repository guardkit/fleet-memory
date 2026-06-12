"""Unit test for fake_embed fixture to verify it works without dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def test_fake_embed_produces_768_dim_vector(fake_embed: Callable[[str], list[float]]) -> None:
    """fake_embed returns 768-dimensional vectors."""
    vector = fake_embed("test input")
    assert len(vector) == 768
    assert all(isinstance(v, float) for v in vector)


def test_fake_embed_is_deterministic(fake_embed: Callable[[str], list[float]]) -> None:
    """Same input always produces same output."""
    text = "deterministic test"
    vec1 = fake_embed(text)
    vec2 = fake_embed(text)
    assert vec1 == vec2


def test_fake_embed_different_inputs_differ(fake_embed: Callable[[str], list[float]]) -> None:
    """Different inputs produce different vectors."""
    vec1 = fake_embed("input one")
    vec2 = fake_embed("input two")
    assert vec1 != vec2


def test_fake_embed_values_in_valid_range(fake_embed: Callable[[str], list[float]]) -> None:
    """Vector values are in typical embedding range [-1, 1]."""
    vector = fake_embed("range test")
    assert all(-1.0 <= v <= 1.0 for v in vector)
