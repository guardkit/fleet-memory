"""Unit tests for embedding functionality.

All tests use httpx.MockTransport - no network calls are made.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from fleet_memory.embed import (
    _CHARS_PER_TOKEN,
    _estimate_tokens,
    _pack_batches,
    embed,
    make_fake_embed,
)
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
    embed_max_batch_tokens: int = 2048,
) -> Settings:
    """Create Settings instance for testing."""
    return Settings(
        pg_dsn="postgresql://test:test@localhost/test",
        embed_url=embed_url,
        embed_model=embed_model,
        embed_dims=embed_dims,
        embed_timeout_s=embed_timeout_s,
        embed_max_batch_tokens=embed_max_batch_tokens,
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


# ---------------------------------------------------------------------------
# Deterministic 4xx classification (TASK-FIX-RELAYDROP01)
#
# A deterministic embed rejection (e.g. exceed_context_size_error) must raise the
# poison-mappable EmbedRequestError, NOT the transient EmbedServiceError — otherwise
# the relay nak-retries it until max_deliver silently drops the episode. 408/429 and
# 5xx stay transient (a retry may succeed).
# ---------------------------------------------------------------------------


def make_error_response(
    status_code: int,
    error_type: str | None = None,
    message: str = "request rejected",
) -> httpx.Response:
    """Build an OpenAI/llama.cpp-style error response: {"error": {type, message}}."""
    error_obj: dict = {"message": message, "code": status_code}
    if error_type is not None:
        error_obj["type"] = error_type
    return httpx.Response(
        status_code=status_code,
        json={"error": error_obj},
        request=httpx.Request("POST", "http://localhost:9000/v1/embeddings"),
    )


@pytest.mark.asyncio
async def test_exceed_context_400_raises_embed_request_error():
    """Reproducer: HTTP 400 exceed_context_size_error → EmbedRequestError (poison-mappable).

    This is the exact failure from the 2026-06-26 harvest: the embed server returns a
    deterministic 400 with n_ctx exceeded. It must classify as EmbedRequestError so the
    relay routes it to the DLQ instead of nak-retrying into a silent drop.
    """
    from fleet_memory.errors import EmbedRequestError

    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return make_error_response(
            400,
            error_type="exceed_context_size_error",
            message="the request exceeds the available context size (n_ctx=2048)",
        )

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedRequestError) as exc_info:
        await embed(["a very long input"], settings, transport=transport)

    error = exc_info.value
    assert error.status_code == 400
    assert error.error_type == "exceed_context_size_error"
    assert "exceed_context_size_error" in str(error)
    assert "n_ctx" in str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 413, 422], ids=["400", "413", "422"])
async def test_deterministic_4xx_raises_embed_request_error(status_code: int):
    """Deterministic 4xx (400/413/422) → EmbedRequestError (won't change on retry)."""
    from fleet_memory.errors import EmbedRequestError

    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return make_error_response(status_code, message="client error")

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedRequestError) as exc_info:
        await embed(["test"], settings, transport=transport)

    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [408, 429, 500, 502, 503],
    ids=["408", "429", "500", "502", "503"],
)
async def test_transient_status_codes_stay_embed_service_error(status_code: int):
    """408/429 and 5xx stay transient EmbedServiceError — NOT the deterministic subclass.

    A retry may yet succeed (timeout, rate limit, transient server error), so these must
    keep nak-retry semantics rather than being dead-lettered.
    """
    from fleet_memory.errors import EmbedRequestError, EmbedServiceError

    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return make_error_response(status_code, message="transient")

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedServiceError) as exc_info:
        await embed(["test"], settings, transport=transport)

    error = exc_info.value
    assert error.status_code == status_code
    # The boundary that matters: transient failures must NOT be the poison subclass.
    assert not isinstance(error, EmbedRequestError)


@pytest.mark.asyncio
async def test_deterministic_4xx_without_error_body_still_classified():
    """A 4xx with no parseable error envelope still raises EmbedRequestError on status alone."""
    from fleet_memory.errors import EmbedRequestError

    settings = make_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=400, content=b"not json", request=request)

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedRequestError) as exc_info:
        await embed(["test"], settings, transport=transport)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_type is None


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


# ---------------------------------------------------------------------------
# Sub-batching token math (TASK-FIX-RELAYBATCH01)
#
# The relay embeds a whole episode's chunks via one embed() call; embed() must
# spread them across multiple requests so no request exceeds the embed server's
# per-slot n_ctx. These tests pin the packing math and the 1-input -> 1-embedding
# contract that prevents multi-chunk episodes from being silently dropped.
# ---------------------------------------------------------------------------


def make_length_encoding_handler(
    dims: int = 768,
    request_log: list[list[str]] | None = None,
):
    """Build a handler that echoes one embedding per input, encoding input length.

    Each input text maps to a vector filled with float(len(text)), so distinct-length
    inputs yield distinguishable vectors — the test can assert output order matches
    input order across batch boundaries. When provided, request_log records the
    ``input`` list of every request, exposing how many sub-batches were sent.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        inputs = body["input"]
        if request_log is not None:
            request_log.append(list(inputs))
        embeddings = [[float(len(text))] * dims for text in inputs]
        return mock_embed_response(embeddings)

    return handler


def test_estimate_tokens_uses_chars_per_token_heuristic():
    """_estimate_tokens approximates tokens as ceil(chars / _CHARS_PER_TOKEN), min 1."""
    assert _estimate_tokens("") == 1  # never zero — empty input still occupies a slot
    assert _estimate_tokens("a") == 1
    assert _estimate_tokens("a" * _CHARS_PER_TOKEN) == 1
    assert _estimate_tokens("a" * (_CHARS_PER_TOKEN * 5)) == 5
    assert _estimate_tokens("a" * (_CHARS_PER_TOKEN * 5 + 1)) == 6  # ceil rounds up


def test_pack_batches_single_batch_when_under_budget():
    """Inputs summing within the budget stay in one batch (one request)."""
    texts = ["a" * 20, "b" * 20]  # 5 + 5 = 10 tokens
    batches = _pack_batches(texts, max_batch_tokens=10)

    assert batches == [["a" * 20, "b" * 20]]


def test_pack_batches_splits_over_budget_each_within_budget():
    """Inputs summing past the budget split into ordered batches, each <= budget."""
    texts = ["a" * 20, "b" * 20, "c" * 20]  # 5 tokens each, budget 10
    batches = _pack_batches(texts, max_batch_tokens=10)

    assert batches == [["a" * 20, "b" * 20], ["c" * 20]]
    for batch in batches:
        assert sum(_estimate_tokens(t) for t in batch) <= 10


def test_pack_batches_empty_input():
    """Empty input yields no batches (and embed() makes no request)."""
    assert _pack_batches([], max_batch_tokens=10) == []


def test_pack_batches_truncates_oversized_single_input(caplog):
    """A single input larger than the whole budget is truncated to fit, with a warning.

    The 1-input -> 1-embedding contract forbids splitting one text into several
    vectors, so the over-budget chunk is truncated (degraded but stored) rather than
    failing the request. DLQ visibility for truly unembeddable inputs is RELAYDROP01.
    """
    budget = 10
    oversized = "z" * (budget * _CHARS_PER_TOKEN * 2)  # ~20 tokens, double the budget

    with caplog.at_level(logging.WARNING, logger="fleet_memory.embed"):
        batches = _pack_batches([oversized], max_batch_tokens=budget)

    assert len(batches) == 1
    assert len(batches[0]) == 1
    # Truncated to the budget's worth of characters → estimate now fits.
    assert len(batches[0][0]) == budget * _CHARS_PER_TOKEN
    assert _estimate_tokens(batches[0][0]) <= budget
    assert "truncat" in caplog.text.lower()


@pytest.mark.asyncio
async def test_embed_single_request_when_under_budget():
    """Small inputs go out as exactly one request (preserves pre-fix behavior)."""
    settings = make_settings(embed_max_batch_tokens=2048)
    request_log: list[list[str]] = []
    transport = httpx.MockTransport(make_length_encoding_handler(request_log=request_log))

    result = await embed(["text one", "text two", "text three"], settings, transport=transport)

    assert len(request_log) == 1  # single batch
    assert len(result) == 3


@pytest.mark.asyncio
async def test_embed_sub_batches_episode_exceeding_n_ctx():
    """Reproducer: an episode whose chunks exceed the budget embeds ALL chunks.

    Pre-fix this was one request that 400s past n_ctx, dropping the whole episode.
    Post-fix the inputs span multiple requests and every chunk gets an embedding,
    returned in input order (len(result) == len(texts)).
    """
    settings = make_settings(embed_max_batch_tokens=10)
    # Distinct lengths so output order is verifiable: 1, 4, 5, 9 tokens.
    texts = ["x" * 4, "y" * 16, "z" * 20, "w" * 36]
    request_log: list[list[str]] = []
    transport = httpx.MockTransport(make_length_encoding_handler(request_log=request_log))

    result = await embed(texts, settings, transport=transport)

    # Greedy packing: [t1,t2,t3] (1+4+5=10) then [t4] (9) → two requests.
    assert request_log == [["x" * 4, "y" * 16, "z" * 20], ["w" * 36]]
    # Every chunk embedded, in input order (first component encodes input length).
    assert len(result) == len(texts)
    assert [vec[0] for vec in result] == [4.0, 16.0, 20.0, 36.0]


@pytest.mark.asyncio
async def test_embed_oversized_chunk_is_truncated_then_embedded(caplog):
    """A lone chunk bigger than n_ctx is truncated and still embedded (not dropped)."""
    settings = make_settings(embed_max_batch_tokens=10)
    oversized = "q" * (10 * _CHARS_PER_TOKEN * 3)  # ~30 tokens, triple the budget
    request_log: list[list[str]] = []
    transport = httpx.MockTransport(make_length_encoding_handler(request_log=request_log))

    with caplog.at_level(logging.WARNING, logger="fleet_memory.embed"):
        result = await embed([oversized], settings, transport=transport)

    assert len(result) == 1  # the chunk still produced an embedding
    assert len(request_log) == 1
    # The request carried the truncated text, not the original oversized one.
    assert len(request_log[0][0]) == 10 * _CHARS_PER_TOKEN
    assert "truncat" in caplog.text.lower()


@pytest.mark.asyncio
async def test_embed_empty_input_makes_no_request():
    """Embedding an empty list returns [] without issuing any request."""
    settings = make_settings()
    request_log: list[list[str]] = []
    transport = httpx.MockTransport(make_length_encoding_handler(request_log=request_log))

    result = await embed([], settings, transport=transport)

    assert result == []
    assert request_log == []
