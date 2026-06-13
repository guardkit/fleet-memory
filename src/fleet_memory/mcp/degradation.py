"""MCP tool degradation wrapper and structured error envelope.

Provides the single reliability primitive for all MCP tools: a `tool_safe`
decorator that catches store/embedding outages and converts them to structured
tool-error results instead of crashing the server.

This enables graceful degradation — tools return structured errors when
dependencies fail, rather than propagating exceptions that would crash the
FastMCP server.

Exception mapping:
  - TimeoutError → "memory store is unavailable" (infrastructure)
  - EmbedServiceError/EmbedTimeoutError → "temporarily unavailable" (infrastructure)
  - ValueError/NamespaceValidationError/UnknownPayloadTypeError → validation message (client error)

All error messages preserve credential hygiene — no DSNs, hosts, or secrets.
"""

from __future__ import annotations

import functools
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from fleet_memory.errors import (
    EmbedServiceError,
    EmbedTimeoutError,
    NamespaceValidationError,
    UnknownPayloadTypeError,
)


@dataclass
class ToolResult:
    """Structured result envelope for MCP tool execution.

    Distinguishes successful executions from errors, and infrastructure
    errors from client errors. Tools return this type to communicate
    both success and graceful degradation.

    Attributes:
        is_error: True if execution failed, False if successful
        error_type: "infrastructure" or "client" (None if is_error=False)
        message: Error message (credential-sanitized) or empty string
        value: The actual result value (None if is_error=True)
    """

    is_error: bool
    error_type: str | None = None
    message: str = ""
    value: Any = None


def _sanitize_message(msg: str) -> str:
    """Remove credentials and connection details from error messages.

    Strips:
      - postgresql:// DSNs (user:pass@host:port patterns)
      - http/https URLs with credentials
      - Standalone host:port patterns
      - Common secret patterns

    Preserves the error message structure while removing sensitive data.
    """
    # Remove postgresql:// DSNs
    msg = re.sub(r"postgresql://[^\s]+", "[DATABASE_DSN_REDACTED]", msg)

    # Remove http(s):// URLs (including credentials)
    msg = re.sub(r"https?://[^\s]+", "[URL_REDACTED]", msg)

    # Remove standalone host:port patterns (e.g., "db.example.com:5432")
    msg = re.sub(r"\b[\w.-]+:\d{2,5}\b", "[HOST_PORT_REDACTED]", msg)

    # Remove paths that might contain secrets
    msg = re.sub(r"/([\w.-]+/)*[\w.-]+\.(key|pem|crt|token)", "[FILE_PATH_REDACTED]", msg)

    return msg


def _map_exception_to_result(exc: Exception) -> ToolResult:
    """Map known exceptions to structured ToolResult.

    Infrastructure errors (retryable):
      - TimeoutError: store unreachable
      - EmbedServiceError/EmbedTimeoutError: embedding service unavailable

    Client errors (non-retryable):
      - ValueError: validation failures
      - NamespaceValidationError/UnknownPayloadTypeError: specific validation errors

    All messages are sanitized to remove credentials.
    """
    # Infrastructure degradation: store unreachable
    if isinstance(exc, TimeoutError) and not isinstance(exc, EmbedTimeoutError):
        return ToolResult(
            is_error=True,
            error_type="infrastructure",
            message="The memory store is unavailable",
        )

    # Infrastructure degradation: embedding service timeout
    if isinstance(exc, EmbedTimeoutError):
        return ToolResult(
            is_error=True,
            error_type="infrastructure",
            message="The operation is temporarily unavailable",
        )

    # Infrastructure degradation: embedding service error
    if isinstance(exc, EmbedServiceError):
        return ToolResult(
            is_error=True,
            error_type="infrastructure",
            message="The operation is temporarily unavailable",
        )

    # Client error: validation failures (preserve validation message)
    if isinstance(exc, (ValueError, NamespaceValidationError, UnknownPayloadTypeError)):
        sanitized = _sanitize_message(str(exc))
        return ToolResult(
            is_error=True,
            error_type="client",
            message=sanitized,
        )

    # Unknown exception type - treat as infrastructure error (fail-safe)
    sanitized = _sanitize_message(str(exc))
    return ToolResult(
        is_error=True,
        error_type="infrastructure",
        message=f"An unexpected error occurred: {sanitized}",
    )


def tool_safe[T](func: Callable[..., T]) -> Callable[..., T | ToolResult]:
    """Decorator that catches exceptions and converts to ToolResult.

    Wraps MCP tool functions to provide graceful degradation. When the
    tool raises a known exception (store timeout, embedding service error,
    validation error), the decorator catches it and returns a structured
    ToolResult instead of crashing the server.

    Supports both sync and async functions.

    Args:
        func: Tool function to wrap (sync or async)

    Returns:
        Wrapped function that returns ToolResult on error, or the
        original return value on success
    """
    if inspect.iscoroutinefunction(func):
        # Async function wrapper
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T | ToolResult:
            try:
                result = await func(*args, **kwargs)
                # Success: wrap in ToolResult
                return ToolResult(is_error=False, value=result)
            except Exception as exc:
                # Graceful degradation: map to structured error
                return _map_exception_to_result(exc)

        return cast(Callable[..., T | ToolResult], async_wrapper)
    else:
        # Sync function wrapper
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T | ToolResult:
            try:
                result = func(*args, **kwargs)
                # Success: wrap in ToolResult
                return ToolResult(is_error=False, value=result)
            except Exception as exc:
                # Graceful degradation: map to structured error
                return _map_exception_to_result(exc)

        return cast(Callable[..., T | ToolResult], sync_wrapper)
