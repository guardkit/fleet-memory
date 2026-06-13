"""memory_write_payload MCP tool: typed payload write through DeterministicWriter.

Exposes memory_write_payload as an MCP tool that validates typed payloads at the
boundary, instantiates registered models via the payload registry, and dispatches
through the existing DeterministicWriter.write — the single write path.

There is no second write path: the tool produces records byte-identical to a relay
write of the same payload.

Producer: TASK-MCP-004
Consumer: Wave-3 MCP integration
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from fleet_memory.mcp.degradation import tool_safe
from fleet_memory.payloads.registry import get_model_for_type

if TYPE_CHECKING:
    from fleet_memory.writer.core import DeterministicWriter


@tool_safe
async def memory_write_payload(
    payload_dict: dict[str, Any],
    writer: DeterministicWriter,
) -> str:
    """Write a typed payload through the deterministic writer.

    Validates the payload at the boundary, resolves the type through the registry,
    instantiates the typed model (ignoring any forged identity fields), and
    dispatches to DeterministicWriter.write.

    On success returns the derived natural key (type:project:identifier).
    Idempotency and content-hash upsert are inherited from the writer.

    Args:
        payload_dict: Raw payload dict from MCP client (must include payload_type)
        writer: DeterministicWriter instance from ServerContext

    Returns:
        The derived natural key (e.g., "adr:my_project:ADR_001")

    Raises:
        ValueError: If payload_type is unknown or validation fails
        IdentifierValidationError: If identifier contains invalid characters
        ValidationError: If required fields are missing
        TimeoutError: If store is unreachable (mapped to infrastructure error)
        EmbedServiceError: If embeddings are unavailable (mapped to infrastructure error)
    """
    # Step 1: Extract and validate payload_type
    if "payload_type" not in payload_dict:
        raise ValueError(
            "payload_type is required: every write must specify a registered payload type"
        )

    payload_type = payload_dict["payload_type"]

    # Step 2: Resolve type through registry (raises UnknownPayloadTypeError if not found)
    model_class = get_model_for_type(payload_type)

    # Step 3: Instantiate typed model (validates all fields, ignores extra like stored_identity)
    # This will raise ValidationError if required fields are missing or invalid
    # IdentifierValidationError will be raised by the model's validators if identifier is invalid
    try:
        payload = model_class(**payload_dict)
    except ValidationError as exc:
        # Convert Pydantic validation error to readable message
        errors = exc.errors()
        if errors:
            first_error = errors[0]
            field = first_error.get("loc", ["unknown"])[0]
            msg = first_error.get("msg", "validation failed")
            raise ValueError(f"Field '{field}' {msg}") from exc
        raise ValueError("Payload validation failed") from exc

    # Step 4: Write through the deterministic writer (single write path)
    # Idempotency, content-hash upsert, and supersession are handled by the writer
    await writer.write(payload)

    # Step 5: Return derived natural key as acknowledgment (ASSUM-006)
    # This is the server-derived identity, never a client-supplied value
    return payload.natural_key


def register(mcp, context) -> None:
    """Register the memory_write_payload tool with the FastMCP server.

    Extension point implementation for TASK-MCP-001.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies
    """

    @mcp.tool()
    async def memory_write_payload_tool(payload: dict) -> dict:
        """Write a typed memory payload through the deterministic writer.

        Validates the payload at the boundary, resolves the type through the registry,
        and writes to the memory store. Returns the derived natural key on success.

        Args:
            payload: Dictionary with payload_type and type-specific fields

        Returns:
            Success: ToolResult with natural_key value
            Error: ToolResult with error details
        """
        # Get writer from server state
        state = mcp.get_state()
        writer = state.get("writer")

        if writer is None:
            return {
                "is_error": True,
                "error_type": "infrastructure",
                "message": "The memory writer is unavailable",
            }

        # Call the wrapped implementation
        result = await memory_write_payload(payload, writer)

        # Return ToolResult directly (FastMCP will serialize it)
        return result
