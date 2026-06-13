"""Unit tests for MCP tool degradation wrapper and error envelope.

Tests the tool_safe decorator that catches exceptions and converts them
to structured tool-error results, ensuring the server degrades gracefully
instead of crashing.
"""

from __future__ import annotations

import pytest


def test_store_timeout_returns_unavailable() -> None:
    """TimeoutError from store returns infrastructure-unavailable result.

    When a tool raises TimeoutError (store unreachable), the wrapper
    should catch it and return a structured error result indicating
    the memory store is unavailable.
    """
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_that_times_out() -> str:
        raise TimeoutError("Connection to postgres timed out")

    result = tool_that_times_out()

    # Should be an error result, not an exception
    assert result.is_error is True
    assert result.error_type == "infrastructure"
    assert "memory store is unavailable" in result.message.lower()
    assert "Connection to postgres timed out" not in result.message


def test_embed_error_returns_temporarily_unavailable() -> None:
    """EmbedServiceError returns infrastructure-unavailable result.

    When embedding service fails, the wrapper should return a structured
    error indicating the operation is temporarily unavailable.
    """
    from fleet_memory.errors import EmbedServiceError
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_that_fails_embed() -> str:
        raise EmbedServiceError("Service unavailable", url="http://embed:9000", status_code=503)

    result = tool_that_fails_embed()

    assert result.is_error is True
    assert result.error_type == "infrastructure"
    assert "temporarily unavailable" in result.message.lower()
    # Should not leak the URL
    assert "http://embed:9000" not in result.message


def test_embed_timeout_returns_temporarily_unavailable() -> None:
    """EmbedTimeoutError returns infrastructure-unavailable result.

    When embedding service times out, wrapper returns structured error.
    """
    from fleet_memory.errors import EmbedTimeoutError
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_with_embed_timeout() -> str:
        raise EmbedTimeoutError("http://embed:9000", timeout_s=5.0)

    result = tool_with_embed_timeout()

    assert result.is_error is True
    assert result.error_type == "infrastructure"
    assert "temporarily unavailable" in result.message.lower()
    # Should not leak URL or timeout details
    assert "http://embed:9000" not in result.message
    assert "5.0" not in result.message


def test_validation_error_returns_client_error() -> None:
    """ValueError for validation returns client-error result with message.

    Validation errors should be surfaced to the client with the specific
    validation message, distinguishable from infrastructure errors.
    """
    from fleet_memory.errors import NamespaceValidationError
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_with_validation_error() -> str:
        raise NamespaceValidationError(
            namespace=("project-123", "memory"), invalid_parts=["project-123"]
        )

    result = tool_with_validation_error()

    assert result.is_error is True
    assert result.error_type == "client"
    # Should contain the validation message
    assert "invalid namespace identifiers" in result.message.lower()
    assert "project-123" in result.message


def test_unknown_payload_type_returns_client_error() -> None:
    """UnknownPayloadTypeError returns client-error result.

    Unknown payload type is a client error - they sent an invalid type.
    """
    from fleet_memory.errors import UnknownPayloadTypeError
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_with_unknown_payload() -> str:
        raise UnknownPayloadTypeError("InvalidType")

    result = tool_with_unknown_payload()

    assert result.is_error is True
    assert result.error_type == "client"
    assert "unknown payload type" in result.message.lower()
    assert "InvalidType" in result.message


def test_generic_value_error_returns_client_error() -> None:
    """Generic ValueError returns client-error result.

    Generic validation errors should be treated as client errors.
    """
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_with_value_error() -> str:
        raise ValueError("Invalid input: must be positive")

    result = tool_with_value_error()

    assert result.is_error is True
    assert result.error_type == "client"
    assert "invalid input: must be positive" in result.message.lower()


def test_wrapper_never_reraises() -> None:
    """Wrapper catches all known exceptions and never re-raises.

    This is the no-crash guarantee - even when dependencies fail,
    the tool returns an error result instead of crashing the server.
    """
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def tool_that_raises() -> str:
        raise TimeoutError("Postgres unreachable")

    # Should not raise - returns error result instead
    result = tool_that_raises()
    assert result.is_error is True


def test_messages_have_no_credentials() -> None:
    """Error messages must not contain DSNs, hosts, ports, or credentials.

    Test against a representative set of errors to ensure credential
    hygiene is maintained in all error paths.
    """
    from fleet_memory.errors import EmbedServiceError, EmbedTimeoutError
    from fleet_memory.mcp.degradation import tool_safe

    # Test TimeoutError with postgres DSN
    @tool_safe
    def tool_with_dsn_error() -> str:
        raise TimeoutError("Connection failed: postgresql://user:secret@db.example.com:5432/fleet")

    result = tool_with_dsn_error()
    # Should not leak DSN components
    assert "postgresql://" not in result.message
    assert "secret" not in result.message
    assert "db.example.com" not in result.message
    assert "5432" not in result.message

    # Test EmbedServiceError with URL
    @tool_safe
    def tool_with_url_error() -> str:
        raise EmbedServiceError("Bad request", url="http://user:pass@embed.internal:9000/v1/embed")

    result2 = tool_with_url_error()
    # Should not leak URL components
    assert "embed.internal" not in result2.message
    assert "9000" not in result2.message
    assert "pass" not in result2.message

    # Test EmbedTimeoutError
    @tool_safe
    def tool_with_timeout() -> str:
        raise EmbedTimeoutError("http://embed.internal:9000", timeout_s=10.0)

    result3 = tool_with_timeout()
    assert "embed.internal" not in result3.message
    assert "9000" not in result3.message


def test_successful_execution_returns_result() -> None:
    """When no exception occurs, wrapper returns the actual result.

    The wrapper should be transparent for successful executions.
    """
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    def successful_tool() -> str:
        return "success"

    result = successful_tool()

    # Should not be an error
    assert result.is_error is False
    assert result.value == "success"


@pytest.mark.asyncio
async def test_async_tool_support() -> None:
    """Wrapper supports async tool functions.

    Many MCP tools will be async, so the wrapper must handle both
    sync and async functions.
    """
    from fleet_memory.mcp.degradation import tool_safe

    @tool_safe
    async def async_tool_that_fails() -> str:
        raise TimeoutError("Async failure")

    result = await async_tool_that_fails()

    assert result.is_error is True
    assert result.error_type == "infrastructure"


@pytest.mark.seam
@pytest.mark.integration_contract("ServerContext")
def test_server_context_shape() -> None:
    """Verify ServerContext exposes the fields tools depend on.

    Contract: ServerContext carries store, writer, settings (built lazily).
    Producer: TASK-MCP-001
    """
    from fleet_memory.mcp.server import ServerContext

    # Consumer side: the envelope and tools only read these attributes.
    for field in ("store", "writer", "settings"):
        assert field in ServerContext.__dataclass_fields__, f"ServerContext must expose '{field}'"
