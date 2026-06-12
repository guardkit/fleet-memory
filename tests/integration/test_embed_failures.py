"""Integration tests for embedding service failure scenarios.

Marker-gated (@pytest.mark.integration) tests validating:
- Embed-down atomicity (no partial writes when embedding fails)
- Dimension mismatch detection (wrong dims causes clean failure)

Requirements:
- Docker running for ephemeral_pg fixture
- Default test run (pytest) skips these; run with: pytest -m integration
"""

from __future__ import annotations

import pytest

from fleet_memory.embed import make_fake_embed
from fleet_memory.errors import EmbedDimensionError, EmbedServiceError
from fleet_memory.store import async_store_context


@pytest.mark.integration
async def test_embed_down_atomicity_no_partial_write(test_settings) -> None:
    """Embed-down atomicity: failing embed raises error with no partial record.

    AC-004 (ASSUM-005): Inject an always-failing embed callable, then verify:
    1. aput of a searchable memory raises an error identifying the embedding service
    2. Subsequent aget for that key returns None (no partial record)
    3. Previously stored memories remain retrievable
    """
    from uuid import uuid4

    # Create a failing embed callable
    async def failing_embed(texts: list[str]) -> list[list[float]]:
        """Always-failing embed function for testing error handling."""
        raise EmbedServiceError(
            "Simulated embedding service failure",
            url="http://localhost:9000/v1/embeddings",
            status_code=503,
        )

    test_namespace = ("fleet_memory", f"test_{uuid4().hex[:8]}", "memory")

    # Use async_store_context with the failing embed callable
    async with async_store_context(test_settings, embed_fn=failing_embed) as store:
        # First, store a memory that will succeed (before we inject failures)
        # Actually, ALL embeds will fail with failing_embed, so we need to test the atomicity
        # Let me re-read the AC...
        # "with an injected always-failing embed callable, aput of a searchable memory raises an error"
        # So the test should:
        # 1. Try to aput with failing embed -> should raise error
        # 2. aget should return None (no partial write)

        # Try to store a memory (should fail due to embed failure)
        test_key = "atomic_test_key"
        test_content = {
            "content": "This memory should not be stored due to embed failure",
            "metadata": {"test": "atomicity"},
        }

        # Verify aput raises an error identifying the embedding service
        with pytest.raises(EmbedServiceError) as exc_info:
            await store.aput(test_namespace, test_key, test_content)

        # Verify error message identifies the embedding service
        assert "embedding service" in str(exc_info.value).lower(), (
            "Error should identify the embedding service"
        )

        # Verify aget returns None (no partial record)
        retrieved = await store.aget(test_namespace, test_key)
        assert retrieved is None, (
            "aget should return None after failed aput - no partial record should exist"
        )


@pytest.mark.integration
async def test_embed_down_preserves_existing_memories(test_settings) -> None:
    """Embed-down atomicity: previously stored memories remain retrievable after embed failure.

    AC-004 (part 3): Verify that an embed failure on a new write does not affect
    previously stored memories.
    """
    from uuid import uuid4

    test_namespace = ("fleet_memory", f"test_{uuid4().hex[:8]}", "memory")

    # First, store a memory with working embeddings
    fake_embed = make_fake_embed(dims=test_settings.embed_dims)
    async with async_store_context(test_settings, embed_fn=fake_embed) as store:
        existing_key = "existing_memory"
        existing_content = {
            "content": "This memory was stored successfully",
            "metadata": {"status": "existing"},
        }
        await store.aput(test_namespace, existing_key, existing_content)

        # Verify it was stored
        retrieved = await store.aget(test_namespace, existing_key)
        assert retrieved is not None, "Existing memory should be stored"
        assert retrieved.value == existing_content

    # Now create a failing embed callable
    async def failing_embed(texts: list[str]) -> list[list[float]]:
        """Always-failing embed function."""
        raise EmbedServiceError(
            "Simulated embed service down",
            url="http://localhost:9000/v1/embeddings",
        )

    # Try to store a new memory with failing embed
    async with async_store_context(test_settings, embed_fn=failing_embed) as store:
        new_key = "new_memory"
        new_content = {
            "content": "This memory should fail to store",
            "metadata": {"status": "new"},
        }

        # Verify new aput fails
        with pytest.raises(EmbedServiceError):
            await store.aput(test_namespace, new_key, new_content)

        # Verify existing memory is still retrievable
        retrieved_existing = await store.aget(test_namespace, existing_key)
        assert retrieved_existing is not None, (
            "Previously stored memories should remain retrievable after embed failure"
        )
        assert retrieved_existing.value == existing_content


@pytest.mark.integration
async def test_dimension_mismatch_no_partial_write(test_settings) -> None:
    """Dimension mismatch: wrong-dims embed causes clean failure with no partial record.

    AC-006: Inject an embed callable that returns wrong dimensions, then verify:
    1. aput raises a dimension mismatch error (from PostgreSQL/pgvector)
    2. aget returns None (no partial record)

    Note: The dimension mismatch is enforced at the PostgreSQL/pgvector level,
    not at the application level, so we expect psycopg.errors.DataException.
    """
    import psycopg.errors
    from uuid import uuid4

    # Create an embed callable that returns wrong dimensions
    wrong_dims = 384  # Different from test_settings.embed_dims (768)

    async def wrong_dims_embed(texts: list[str]) -> list[list[float]]:
        """Embed function that returns wrong dimensions."""
        # Return embeddings with wrong dimension count
        return [[0.1] * wrong_dims for _ in texts]

    test_namespace = ("fleet_memory", f"test_{uuid4().hex[:8]}", "memory")

    # Use async_store_context with wrong-dims embed callable
    async with async_store_context(test_settings, embed_fn=wrong_dims_embed) as store:
        test_key = "dimension_mismatch_key"
        test_content = {
            "content": "This memory should fail due to dimension mismatch",
            "metadata": {"test": "dimensions"},
        }

        # Verify aput raises a dimension mismatch error
        # The error comes from PostgreSQL/pgvector when trying to insert wrong-dimension vector
        with pytest.raises(psycopg.errors.DataException) as exc_info:
            await store.aput(test_namespace, test_key, test_content)

        # Verify error message mentions dimension mismatch
        error_msg = str(exc_info.value)
        assert "dimension" in error_msg.lower(), (
            f"Error should mention dimensions, got: {error_msg}"
        )
        assert str(wrong_dims) in error_msg or str(test_settings.embed_dims) in error_msg, (
            f"Error should mention the dimension values, got: {error_msg}"
        )

        # Verify no partial record was written
        retrieved = await store.aget(test_namespace, test_key)
        assert retrieved is None, (
            "No partial record should exist after dimension mismatch error"
        )
