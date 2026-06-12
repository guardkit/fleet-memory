"""Embedding functionality for fleet-memory.

Provides async httpx-based embedding against OpenAI-compatible /v1/embeddings endpoint.
"""

from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

import httpx

from fleet_memory.errors import (
    EmbedDimensionError,
    EmbedServiceError,
    EmbedTimeoutError,
)

if TYPE_CHECKING:
    from fleet_memory.settings import Settings


def _normalize_embed_url(base_url: str) -> str:
    """Normalize base URL to .../v1/embeddings endpoint.

    Args:
        base_url: Base URL (e.g., "http://localhost:9000" or "http://localhost:9000/v1")

    Returns:
        Full embeddings endpoint URL
    """
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return f"{base_url}/embeddings"
    if base_url.endswith("/v1/embeddings"):
        return base_url
    return f"{base_url}/v1/embeddings"


async def embed(
    texts: list[str],
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[list[float]]:
    """Embed texts using OpenAI-compatible API with dimension validation.

    Args:
        texts: List of texts to embed
        settings: Configuration including embed_url, embed_model, embed_dims, embed_timeout_s
        transport: Optional httpx transport (for testing with MockTransport)

    Returns:
        List of embedding vectors (one per input text)

    Raises:
        EmbedDimensionError: If any embedding dimension doesn't match settings.embed_dims
        EmbedTimeoutError: If request times out
        EmbedServiceError: If service returns error or malformed response
    """
    url = _normalize_embed_url(settings.embed_url)

    # Configure timeout: read timeout controls model inference time (ASSUM-008)
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.embed_timeout_s,
        write=5.0,
        pool=5.0,
    )

    # Build OpenAI-compatible request
    request_body = {
        "model": settings.embed_model,
        "input": texts,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.post(url, json=request_body)

        # Check HTTP status
        if response.status_code != 200:
            raise EmbedServiceError(
                "HTTP error from embedding service",
                url=url,
                status_code=response.status_code,
            )

        # Parse JSON response
        try:
            data = response.json()
        except Exception as e:
            raise EmbedServiceError(
                f"Malformed JSON response: {e}",
                url=url,
            ) from e

        # Extract embeddings
        if "data" not in data:
            raise EmbedServiceError(
                "Response missing 'data' field",
                url=url,
            )

        embeddings = [item["embedding"] for item in data["data"]]

        # Validate dimensions
        for i, embedding in enumerate(embeddings):
            actual_dims = len(embedding)
            if actual_dims != settings.embed_dims:
                raise EmbedDimensionError(
                    actual=actual_dims,
                    expected=settings.embed_dims,
                )

        return embeddings

    except httpx.ReadTimeout as e:
        raise EmbedTimeoutError(
            url=url,
            timeout_s=settings.embed_timeout_s,
        ) from e
    except httpx.ConnectTimeout as e:
        raise EmbedTimeoutError(
            url=url,
            timeout_s=settings.embed_timeout_s,
        ) from e
    except (EmbedDimensionError, EmbedTimeoutError, EmbedServiceError):
        # Re-raise our custom exceptions
        raise
    except Exception as e:
        # Catch any other unexpected errors
        raise EmbedServiceError(
            f"Unexpected error: {type(e).__name__}: {e}",
            url=url,
        ) from e


def make_fake_embed(dims: int = 768) -> callable:
    """Create a deterministic, network-free embed callable for testing.

    Returns unit-norm vectors derived from text hash for stable ranking tests.

    Args:
        dims: Embedding dimensions (default 768)

    Returns:
        Async callable matching embed signature: async (list[str]) -> list[list[float]]
    """

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        """Deterministic fake embed function.

        Args:
            texts: List of texts to embed

        Returns:
            List of deterministic unit-norm embedding vectors
        """
        embeddings = []
        for text in texts:
            # Generate deterministic vector from text hash
            hash_digest = hashlib.sha256(text.encode()).digest()
            # Use hash bytes to seed vector components
            vector = []
            for i in range(dims):
                # Use different bytes for each dimension
                byte_idx = (i * 2) % len(hash_digest)
                # Convert bytes to float in [-1, 1]
                if byte_idx + 1 < len(hash_digest):
                    value = (
                        int.from_bytes(
                            hash_digest[byte_idx : byte_idx + 2],
                            byteorder="big",
                        )
                        / 32768.0
                        - 1.0
                    )
                else:
                    value = hash_digest[byte_idx] / 128.0 - 1.0
                vector.append(value)

            # Normalize to unit length
            magnitude = math.sqrt(sum(x * x for x in vector))
            if magnitude > 0:
                vector = [x / magnitude for x in vector]
            else:
                # Fallback: all zeros -> unit vector in first dimension
                vector = [1.0] + [0.0] * (dims - 1)

            embeddings.append(vector)

        return embeddings

    return fake_embed
