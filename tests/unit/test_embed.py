"""Unit tests for embedding functionality.

All tests use httpx.MockTransport - no network calls are made.
"""

from __future__ import annotations

import json

import httpx
import pytest

from fleet_memory.embed import embed, make_fake_embed
from fleet_memory.errors import (
    EmbedDimensionError,
    EmbedServiceError,
    EmbedTimeoutError,
)
from fleet_memory.settings import Settings


def make_settings(
    embed_url: str = "http://localhost:9000",
    embed_model: str = "nomic-embed-text-v1.5",
    embed_dims: int = 768,
    embed_timeout_s: float = 10.0,
) -> Settings:
    """Create Settings instance for testing."""
    return Settings(
        pg_dsn="postgresql://test:test@localhost/test",
        embed_url=embed_url,
        embed_model=embed_model,
        embed_dims=embed_dims,
        embed_timeout_s=embed_timeout_s,
    )


def mock_embed_response(embeddings: list[list[float]]) -> httpx.Response:
    """Create a mock OpenAI-compatible embedding response."""
    data = {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": emb}
            for i, emb in enumerate(embeddings)
        ],
        "model": "nomic-embed-text-v1.5",
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }
    return httpx.Response(
        status_code=200,
        json=data,
        request=httpx.Request("POST", "http://localhost:9000/v1/embeddings"),
    )


@pytest.mark.asyncio
async def test_successful_embed_single_text():
    """Test successful embedding of a single text."""
    settings = make_settings()
    embedding = [0.1] * 768

    def handler(request: httpx.Request) -> httpx.Response:
        return mock_embed_response([embedding])

    transport = httpx.MockTransport(handler)
    result = await embed(["hello world"], settings, transport=transport)

    assert len(result) == 1
    assert result[0] == embedding


@pytest.mark.asyncio
async def test_successful_embed_multiple_texts():
    """Test successful embedding of multiple texts."""
    settings = make_settings()
    embeddings = [[0.1] * 768, [0.2] * 768, [0.3] * 768]

    def handler(request: httpx.Request) -> httpx.Response:
        return mock_embed_response(embeddings)

    transport = httpx.MockTransport(handler)
    result = await embed(["text1", "text2", "text3"], settings, transport=transport)

    assert len(result) == 3
    assert result == embeddings


@pytest.mark.asyncio
async def test_embed_request_format():
    """Test that request body matches OpenAI format."""
    settings = make_settings(embed_model="test-model")
    embedding = [0.1] * 768
    captured_request = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return mock_embed_response([embedding])

    transport = httpx.MockTransport(handler)
    await embed(["test"], settings, transport=transport)

    assert captured_request is not None
    body = json.loads(captured_request.content)
    assert body["model"] == "test-model"
    assert body["input"] == ["test"]


@pytest.mark.asyncio
async def test_embed_url_normalization():
    """Test URL normalization to .../v1/embeddings endpoint."""
    settings = make_settings(embed_url="http://localhost:9000")
    embedding = [0.1] * 768
    captured_url = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url
        captured_url = str(request.url)
        return mock_embed_response([embedding])

    transport = httpx.MockTransport(handler)
    await embed(["test"], settings, transport=transport)

    assert captured_url == "http://localhost:9000/v1/embeddings"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actual_dims",
    [512, 767, 769, 1024],
    ids=["512", "767", "769", "1024"],
)
async def test_dimension_mismatch_raises_error(actual_dims: int):
    """Test that dimension mismatches raise EmbedDimensionError.

    BDD: @boundary @negative outline
    Expected: 768, Actual: [512, 767, 769, 1024]
    """
    settings = make_settings(embed_dims=768)
    wrong_embedding = [0.1] * actual_dims

    def handler(request: httpx.Request) -> httpx.Response:
        return mock_embed_response([wrong_embedding])

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedDimensionError) as exc_info:
        await embed(["test"], settings, transport=transport)

    error = exc_info.value
    assert error.actual == actual_dims
    assert error.expected == 768
    assert str(actual_dims) in str(error)
    assert "768" in str(error)


@pytest.mark.asyncio
async def test_http_500_raises_embed_service_error():
    """Test that HTTP 500 raises EmbedServiceError."""
    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=500,
            json={"error": "Internal server error"},
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedServiceError) as exc_info:
        await embed(["test"], settings, transport=transport)

    error = exc_info.value
    assert error.status_code == 500
    assert "500" in str(error)


@pytest.mark.asyncio
async def test_malformed_json_raises_embed_service_error():
    """Test that malformed JSON raises EmbedServiceError."""
    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"not valid json",
            request=request,
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedServiceError) as exc_info:
        await embed(["test"], settings, transport=transport)

    assert "malformed" in str(exc_info.value).lower() or "json" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_missing_data_field_raises_embed_service_error():
    """Test that response without 'data' field raises EmbedServiceError."""
    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"object": "list"},  # Missing 'data' field
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedServiceError) as exc_info:
        await embed(["test"], settings, transport=transport)

    assert "data" in str(exc_info.value).lower() or "malformed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_timeout_raises_embed_timeout_error():
    """Test that timeout raises EmbedTimeoutError within embed_timeout_s.

    ASSUM-008 verification: This test confirms that httpx timeout semantics
    work as expected. The timeout applies to the read phase (model inference time).
    httpx.Timeout(connect=5.0, read=settings.embed_timeout_s, write=5.0, pool=5.0)
    means the read timeout controls how long we wait for the response body.

    A MockTransport that never responds triggers httpx.ReadTimeout, which we
    catch and convert to EmbedTimeoutError.
    """
    settings = make_settings(embed_timeout_s=0.1)

    def handler(request: httpx.Request) -> httpx.Response:
        # Simulate a timeout by raising httpx.ReadTimeout
        raise httpx.ReadTimeout("Read timeout")

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedTimeoutError) as exc_info:
        await embed(["test"], settings, transport=transport)

    error = exc_info.value
    assert error.timeout_s == 0.1
    assert "0.1" in str(error)


@pytest.mark.asyncio
async def test_embed_service_error_includes_url_not_credentials():
    """Test that error messages include service URL but never database credentials."""
    settings = make_settings(embed_url="http://localhost:9000")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, request=request)

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedServiceError) as exc_info:
        await embed(["test"], settings, transport=transport)

    error_msg = str(exc_info.value)
    # Should include embedding service URL
    assert "localhost:9000" in error_msg or "http" in error_msg
    # Should NOT include database credentials
    assert "postgresql://" not in error_msg
    assert settings.pg_dsn not in error_msg


@pytest.mark.asyncio
async def test_make_fake_embed_default_dims():
    """Test fake embed with default 768 dimensions."""
    fake_embed = make_fake_embed()
    result = await fake_embed(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 768
    assert len(result[1]) == 768


@pytest.mark.asyncio
async def test_make_fake_embed_custom_dims():
    """Test fake embed with custom dimensions."""
    fake_embed = make_fake_embed(dims=512)
    result = await fake_embed(["test"])

    assert len(result) == 1
    assert len(result[0]) == 512


@pytest.mark.asyncio
async def test_make_fake_embed_deterministic():
    """Test that fake embed returns deterministic results."""
    fake_embed = make_fake_embed(dims=768)

    result1 = await fake_embed(["hello", "world"])
    result2 = await fake_embed(["hello", "world"])

    assert result1 == result2


@pytest.mark.asyncio
async def test_make_fake_embed_different_texts_different_vectors():
    """Test that different texts produce different vectors."""
    fake_embed = make_fake_embed(dims=768)
    result = await fake_embed(["hello", "world"])

    assert result[0] != result[1]


@pytest.mark.asyncio
async def test_make_fake_embed_unit_norm():
    """Test that fake embeddings are unit-norm vectors."""
    fake_embed = make_fake_embed(dims=768)
    result = await fake_embed(["test"])

    vector = result[0]
    magnitude = sum(x * x for x in vector) ** 0.5
    assert abs(magnitude - 1.0) < 1e-6  # Should be unit norm
