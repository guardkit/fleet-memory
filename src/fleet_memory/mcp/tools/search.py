"""memory_search MCP tool for fleet-memory retrieval.

Exposes memory_search as an MCP tool that wraps the FEAT-MEM-05 retrieval
surface (fleet_memory.retrieval.search + assemble_context). The tool builds a
SearchRequest, runs filtered vector search, assembles a token-budgeted context
block, and returns the block plus coverage score.

Features:
- Default token budget of 2000 when client omits it (ASSUM-001)
- Excludes superseded memories by default (ASSUM-008)
- Returns empty results (not errors) for no matches
- Graceful degradation when store/embed services are down (via TASK-MCP-002)

Producer: TASK-MCP-003
Consumer: Claude Desktop MCP client
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fleet_memory.mcp.degradation import tool_safe
from fleet_memory.retrieval import SearchRequest, SearchResult, assemble_context, search

if TYPE_CHECKING:
    from fleet_memory.mcp.server import ServerContext

# Default token budget when client omits it (ASSUM-001)
DEFAULT_TOKEN_BUDGET = 2000


@tool_safe
async def memory_search(
    project: str,
    query: str | None = None,
    payload_types: list[str] | None = None,
    domain_tags: list[str] | None = None,
    token_budget: int | None = None,
    include_superseded: bool = False,
    search_callable: Callable[[SearchRequest, Any], list[SearchResult]] | None = None,
    context: "ServerContext | None" = None,
) -> dict[str, Any]:
    """Search fleet-memory and return token-budgeted context block.

    Wraps the retrieval surface (search + assemble_context) to provide MCP
    clients with a single tool for searching project memories and assembling
    results into a context block that fits within a token budget.

    Args:
        project: Project identifier (underscores only, no hyphens)
        query: Search query string (optional if filters provided)
        payload_types: Filter by payload types (empty = all types)
        domain_tags: Filter by domain tags (empty = no tag filter)
        token_budget: Max tokens in assembled block (default: 2000)
        include_superseded: Include superseded memories (default: False)
        search_callable: Injected search function (for testing, uses real search by default)
        context: ServerContext with store/writer/settings (injected by FastMCP)

    Returns:
        Dict with keys:
            - context_block: Assembled context string (within token budget)
            - coverage_score: Fraction of budget filled (0.0-1.0)
            - contributing_types: Set of payload types that contributed
            - tokens_used: Actual tokens consumed

    Raises:
        (Wrapped by @tool_safe):
        - TimeoutError: Store unreachable → "memory store unavailable"
        - EmbedServiceError: Embeddings down → "search temporarily unavailable"
        - ValueError: Validation failures → client error with validation message

    Example:
        >>> result = await memory_search(
        ...     project="guardkit",
        ...     query="retry logic",
        ...     token_budget=2000
        ... )
        >>> print(result["context_block"])
        >>> print(f"Coverage: {result['coverage_score']:.0%}")
    """
    # Apply default token budget if not provided (ASSUM-001)
    if token_budget is None:
        token_budget = DEFAULT_TOKEN_BUDGET

    # Normalize empty lists
    if payload_types is None:
        payload_types = []
    if domain_tags is None:
        domain_tags = []

    # Build SearchRequest (validation happens here)
    request = SearchRequest(
        project=project,
        query=query,
        payload_types=payload_types,
        domain_tags=domain_tags,
        token_budget=token_budget,
        include_superseded=include_superseded,
    )

    # Use injected search callable (for testing) or default to real search
    search_fn = search_callable if search_callable is not None else search

    # Get store from context
    if context is None:
        raise ValueError("ServerContext is required")
    if context.store is None:
        raise ValueError("Store is not available in ServerContext")

    # Execute search (may raise TimeoutError or EmbedServiceError)
    # These exceptions propagate to @tool_safe wrapper for degradation handling
    results = await search_fn(request, context.store)

    # Assemble context block from ranked results
    assembly = assemble_context(results, token_budget)

    # Return structured result
    return {
        "context_block": assembly.context_block,
        "coverage_score": assembly.coverage_score,
        "contributing_types": list(assembly.contributing_types),  # Convert set to list for JSON
        "tokens_used": assembly.tokens_used,
    }


def register(mcp: Any, context: Any) -> None:
    """Register memory_search tool on the FastMCP server.

    Extension point for TASK-MCP-001's register_all dispatcher.
    Adds the memory_search tool to the MCP server with proper wiring.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies (store, writer, settings)

    Example (called from server.py::register_all):
        from fleet_memory.mcp.tools import search_tool
        search_tool.register(mcp, context)
    """

    @mcp.tool()
    async def memory_search_tool(
        project: str,
        query: str | None = None,
        payload_types: list[str] | None = None,
        domain_tags: list[str] | None = None,
        token_budget: int | None = None,
        include_superseded: bool = False,
    ) -> dict[str, Any]:
        """Search fleet-memory and return token-budgeted context block.

        Args:
            project: Project identifier (underscores only, no hyphens)
            query: Search query string (optional if filters provided)
            payload_types: Filter by payload types (empty = all types)
            domain_tags: Filter by domain tags (empty = no tag filter)
            token_budget: Max tokens in assembled block (default: 2000)
            include_superseded: Include superseded memories (default: False)

        Returns:
            Dict with context_block, coverage_score, contributing_types, tokens_used
        """
        # Get context from server state
        state = mcp.get_state()
        store = state.get("store")

        # Build ServerContext from state
        from fleet_memory.mcp.server import ServerContext

        server_context = ServerContext(
            store=store,
            writer=state.get("writer"),
            settings=state.get("settings"),
        )

        # Call the core search function (wrapped by @tool_safe)
        result = await memory_search(
            project=project,
            query=query,
            payload_types=payload_types,
            domain_tags=domain_tags,
            token_budget=token_budget,
            include_superseded=include_superseded,
            search_callable=None,  # Use real search
            context=server_context,
        )

        # Return the result (already wrapped by @tool_safe)
        return result
