"""MCP resources: discoverable URIs for memory data.

Provides the memory://projects resource that lists projects with memories.
Resources are read-only discovery endpoints for Desktop clients.

Producer: TASK-MCP-006
Consumer: Desktop clients via stdio MCP
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fleet_memory.mcp.degradation import tool_safe

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from fleet_memory.mcp.server import ServerContext


@tool_safe
async def _read_projects(context: ServerContext) -> list[str]:
    """Read the list of projects that have memories in the store.

    Uses list_namespaces to discover distinct project segments from
    the fleet_memory namespace. The namespace shape is:
    ("fleet_memory", project, payload_type)

    Args:
        context: ServerContext with store dependency

    Returns:
        Sorted list of project identifiers

    Raises:
        TimeoutError: If store is unreachable (wrapped by tool_safe)
    """
    if context.store is None:
        # Degraded mode: no store available
        raise TimeoutError("Store is not initialized")

    # List namespaces with fleet_memory prefix
    # This returns tuples like ("fleet_memory", "guardkit", "Document")
    namespaces = await context.store.list_namespaces(
        prefix=("fleet_memory",),
        max_depth=2,  # Only go to project level
        limit=1000,  # Should be enough for listing projects
    )

    # Extract unique project names (second element of namespace tuple)
    # Filter to only include 2-segment namespaces (fleet_memory, project)
    # or 3-segment namespaces (fleet_memory, project, payload_type)
    projects = {ns[1] for ns in namespaces if len(ns) >= 2}

    # Return sorted list for consistent ordering
    return sorted(projects)


def register_projects_resource(mcp: FastMCP, context: ServerContext) -> None:
    """Register the memory://projects resource with the MCP server.

    Registers a resource at URI memory://projects that lists projects
    with memories. The resource read is wrapped with tool_safe for
    graceful degradation when the store is unreachable.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with store dependency
    """

    @mcp.resource("memory://projects")
    async def projects_resource() -> str:
        """List projects that have memories in the store.

        Returns:
            JSON array of project identifiers, or error envelope

        Example successful response:
            ["guardkit", "nats-core", "fleet-memory"]

        Example error response (when store is down):
            {
                "is_error": true,
                "error_type": "infrastructure",
                "message": "The memory store is unavailable"
            }
        """
        result = await _read_projects(context)

        # Check if we got an error result from tool_safe wrapper
        if hasattr(result, "is_error") and result.is_error:
            # Return error as JSON
            import json

            return json.dumps(
                {
                    "is_error": result.is_error,
                    "error_type": result.error_type,
                    "message": result.message,
                }
            )

        # Success: return the list of projects as JSON
        import json

        return json.dumps(result.value)
