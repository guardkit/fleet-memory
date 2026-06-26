"""Embedding functionality for fleet-memory.

Provides async httpx-based embedding against OpenAI-compatible /v1/embeddings endpoint.
"""

from __future__ import annotations

import hashlib
import logging
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

logger = logging.getLogger(__name__)

# Approximate characters per BPE token for English prose. Used only to bound an
# embed request's size against the server's per-slot n_ctx (TASK-FIX-RELAYBATCH01);
# the real token count is the server's concern, so the configured batch budget keeps
# headroom below n_ctx to absorb the error in this heuristic.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Estimate the token cost of a text for batch-budget packing.

    Uses a conservative chars/token heuristic (not an exact tokenizer): the value
    only needs to be good enough to keep a batch under the server's n_ctx, and the
    configured budget leaves headroom. A non-empty text always costs >= 1 token so
    that empty/whitespace inputs still occupy a slot.
    """
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def _pack_batches(texts: list[str], max_batch_tokens: int) -> list[list[str]]:
    """Greedily pack texts into sub-batches each within max_batch_tokens.

    Makes embed request size independent of episode size: instead of one unbounded
    batch (which 400s once an episode's chunks sum past the embed server's per-slot
    n_ctx, silently dropping the whole episode — TASK-FIX-RELAYBATCH01), inputs are
    spread across as many requests as needed, each <= the token budget.

    A single text whose own estimate exceeds the budget cannot be split here without
    breaking the 1-input -> 1-embedding contract, so it is truncated to fit and a
    WARNING is logged (degraded embedding, but the chunk still stores rather than
    failing the request). The heading-aware chunker can emit such an over-target
    section; surfacing genuinely unembeddable inputs via the DLQ is the sibling
    task's job (TASK-FIX-RELAYDROP01).

    Args:
        texts: Inputs to embed, in order.
        max_batch_tokens: Per-request token budget (must be > 0).

    Returns:
        List of batches (each a list of texts), preserving input order. Each batch's
        summed estimate is <= max_batch_tokens. Empty input yields an empty list.
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for text in texts:
        estimate = _estimate_tokens(text)

        # Oversized single input: truncate-with-warning so the request still succeeds.
        if estimate > max_batch_tokens:
            max_chars = max_batch_tokens * _CHARS_PER_TOKEN
            logger.warning(
                "Embed input exceeds per-request token budget; truncating "
                "(~%d tokens > budget %d; %d -> %d chars). Embedding quality "
                "degraded for this chunk.",
                estimate,
                max_batch_tokens,
                len(text),
                max_chars,
            )
            text = text[:max_chars]
            estimate = _estimate_tokens(text)

        # Flush the current batch before it would overflow the budget.
        if current and current_tokens + estimate > max_batch_tokens:
            batches.append(current)
            current = []
            current_tokens = 0

        current.append(text)
        current_tokens += estimate

    if current:
        batches.append(current)

    return batches


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


async def _embed_request(
    client: httpx.AsyncClient,
    url: str,
    texts: list[str],
    settings: Settings,
) -> list[list[float]]:
    """Issue one /v1/embeddings request for a single (budget-bounded) sub-batch.

    Sends exactly the given texts, validates the response shape and per-vector
    dimensions, and returns embeddings in response order. Callers are responsible
    for keeping ``texts`` within the server's per-slot n_ctx (see _pack_batches).

    Raises:
        EmbedDimensionError: If any embedding dimension doesn't match settings.embed_dims
        EmbedServiceError: If the service returns a non-200 or a malformed response
    """
    request_body = {
        "model": settings.embed_model,
        "input": texts,
    }

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
    for embedding in embeddings:
        actual_dims = len(embedding)
        if actual_dims != settings.embed_dims:
            raise EmbedDimensionError(
                actual=actual_dims,
                expected=settings.embed_dims,
            )

    return embeddings


async def embed(
    texts: list[str],
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[list[float]]:
    """Embed texts using OpenAI-compatible API with dimension validation.

    Inputs are greedily sub-batched so no single request exceeds
    ``settings.embed_max_batch_tokens`` (TASK-FIX-RELAYBATCH01). An episode whose
    chunks sum past the embed server's per-slot n_ctx is therefore spread across
    several requests instead of one batch that 400s and drops the whole episode.
    The 1-input -> 1-embedding contract holds: embeddings are concatenated in
    input order and ``len(result) == len(texts)``.

    Args:
        texts: List of texts to embed
        settings: Configuration including embed_url, embed_model, embed_dims,
            embed_timeout_s, embed_max_batch_tokens
        transport: Optional httpx transport (for testing with MockTransport)

    Returns:
        List of embedding vectors (one per input text, in input order)

    Raises:
        EmbedDimensionError: If any embedding dimension doesn't match settings.embed_dims
        EmbedTimeoutError: If a request times out
        EmbedServiceError: If the service returns an error or malformed response
    """
    if not texts:
        return []

    url = _normalize_embed_url(settings.embed_url)

    # Configure timeout: read timeout controls model inference time (ASSUM-008)
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.embed_timeout_s,
        write=5.0,
        pool=5.0,
    )

    # Partition inputs so each request stays within the per-slot n_ctx budget.
    batches = _pack_batches(texts, settings.embed_max_batch_tokens)

    embeddings: list[list[float]] = []
    try:
        # One client across all sub-batches so connections are reused.
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            for batch in batches:
                embeddings.extend(await _embed_request(client, url, batch, settings))

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
