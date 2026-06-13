"""MCP tool for declared supersession.

Exposes memory_supersede that declares supersession (RD-6: declared, never
inferred) by dispatching to apply_supersessions. The tool validates the
supersession declaration at the boundary — natural-key shape, non-empty
predecessor list, no self-supersession — then applies the links.

Forward supersession is supported: declaring against a not-yet-written
predecessor is accepted and takes effect once the predecessor is written.

Producer: TASK-MCP-005
Consumer: MCP clients via FastMCP server
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fleet_memory.mcp.degradation import ToolResult, tool_safe
from fleet_memory.writer.supersession import apply_supersessions

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore


def _validate_natural_key(key: str) -> bool:
    """Validate natural key format: type:project:identifier.

    Args:
        key: Natural key string to validate

    Returns:
        True if valid format, False otherwise
    """
    segments = key.split(":")
    return len(segments) == 3 and all(segments)


@tool_safe
async def memory_supersede(
    store: AsyncPostgresStore,
    successor_key: str,
    predecessor_keys: list[str],
) -> str:
    """Declare that a newer memory supersedes older ones.

    Marks predecessors as superseded by the successor. The superseded
    memories no longer appear in default search results. Forward
    supersession is supported: declaring supersession of a not-yet-written
    predecessor is accepted.

    Args:
        store: AsyncPostgresStore instance
        successor_key: Natural key of the successor (format: type:project:identifier)
        predecessor_keys: List of predecessor natural keys to mark as superseded

    Returns:
        Success message indicating number of predecessors marked

    Raises:
        ValueError: If validation fails (empty list, malformed key, self-supersession)
        TimeoutError: If store is unavailable (wrapped to ToolResult by @tool_safe)
    """
    # Validate: at least one predecessor is required (ASSUM-005)
    if not predecessor_keys:
        raise ValueError("At least one predecessor is required")

    # Validate: successor key format
    if not _validate_natural_key(successor_key):
        raise ValueError(
            f"Successor '{successor_key}' is not a valid memory key: "
            f"expected format type:project:identifier"
        )

    # Validate: all predecessor keys format
    for pred_key in predecessor_keys:
        if not _validate_natural_key(pred_key):
            raise ValueError(
                f"Predecessor '{pred_key}' is not a valid memory key: "
                f"expected format type:project:identifier"
            )

    # Validate: no self-supersession
    if successor_key in predecessor_keys:
        raise ValueError("A memory cannot supersede itself")

    # Apply supersession via the existing function
    await apply_supersessions(store, successor_key, predecessor_keys)

    # Return success message
    count = len(predecessor_keys)
    plural = "predecessor" if count == 1 else "predecessors"
    return f"Marked {count} {plural} as superseded by {successor_key}"


def register(mcp, context) -> None:
    """Register the memory_supersede tool with the FastMCP server.

    Extension point implementation for TASK-MCP-001.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies
    """

    @mcp.tool()
    async def memory_supersede_tool(
        successor_key: str,
        predecessor_keys: list[str],
    ) -> ToolResult:
        """Declare that a newer memory supersedes older ones.

        Marks predecessors as superseded by the successor. Superseded memories
        no longer appear in default search results.

        Args:
            successor_key: Natural key of the successor (format: type:project:identifier)
            predecessor_keys: List of predecessor natural keys to mark as superseded

        Returns:
            ToolResult with success message or error details
        """
        # Get store from server state
        state = mcp.get_state()
        store = state.get("store")

        if store is None:
            return ToolResult(
                is_error=True,
                error_type="infrastructure",
                message="The memory store is unavailable",
            )

        # Call the wrapped implementation
        return await memory_supersede(store, successor_key, predecessor_keys)
