"""memory_search and memory_search_items MCP tools for fleet-memory retrieval.

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
from fleet_memory.mcp.doors import check_door_project
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
    allowed_projects: frozenset[str] | None = None,
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
        allowed_projects: on a sandbox's own door, the only projects it serves;
            any other ``project`` is refused before anything is searched.
            None (the main server and the single narrow door) serves every project.

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
    # A sandbox's own door serves only its own projects (17 October 2026)
    check_door_project(project, allowed_projects)

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


@tool_safe
async def memory_search_items(
    project: str,
    query: str | None = None,
    payload_types: list[str] | None = None,
    domain_tags: list[str] | None = None,
    token_budget: int | None = None,
    include_superseded: bool = False,
    require_substantive: bool = False,
    search_callable: Callable[[SearchRequest, Any], list[SearchResult]] | None = None,
    context: "ServerContext | None" = None,
    allowed_projects: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Search fleet-memory and return the ranked results one by one.

    ``memory_search`` assembles its results into one block, which is what a
    person reading memory wants. A client that scores, filters and cuts each
    result on its own (GuardKit's builds) needs the results themselves. A
    build sandbox that holds no database address reads memory through this
    tool, so it returns exactly what the library's own search returns, in the
    same order: each result's natural key, its content and its score.

    Takes the arguments of ``memory_search``, plus ``require_substantive``,
    which drops records that carry no usable prose (the same opt-in filter
    the library offers). ``token_budget`` assembles nothing here; it is
    accepted so a request is valid for both tools. ``allowed_projects`` is
    the sandbox door's own list, as for ``memory_search``.

    Returns:
        ``{"items": [{"value": {"natural_key", "content"}, "score"}, ...]}``
        in ranked order. Errors come back in the shared tool error envelope
        (via ``@tool_safe``), exactly as ``memory_search`` reports them.
    """
    check_door_project(project, allowed_projects)
    request = SearchRequest(
        project=project,
        query=query,
        payload_types=payload_types or [],
        domain_tags=domain_tags or [],
        token_budget=token_budget if token_budget is not None else DEFAULT_TOKEN_BUDGET,
        include_superseded=include_superseded,
        require_substantive=require_substantive,
    )
    search_fn = search_callable if search_callable is not None else search
    if context is None:
        raise ValueError("ServerContext is required")
    if context.store is None:
        raise ValueError("Store is not available in ServerContext")

    results = await search_fn(request, context.store)
    return {
        "items": [
            {
                "value": {
                    "natural_key": item.value.get("natural_key"),
                    "content": item.value.get("content"),
                },
                "score": item.score,
            }
            for item in results
        ]
    }


def register(mcp: Any, context: Any, allowed_projects: frozenset[str] | None = None) -> None:
    """Register the memory_search and memory_search_items tools on the FastMCP server.

    Extension point for TASK-MCP-001's register_all dispatcher.
    Adds the memory_search tool to the MCP server with proper wiring.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies (store, writer, settings)
        allowed_projects: a sandbox's own door: the only projects both searches
            serve. None serves every project, as before.

    Example (called from server.py::register_all):
        from fleet_memory.mcp.tools import search_tool
        search_tool.register(mcp, context)
    """

    # Registered under the canonical name every command spec selects
    # (mcp__fleet_memory__memory_search). The inner function keeps a distinct
    # name so it cannot shadow the module-level core function it calls.
    @mcp.tool(name="memory_search")
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
        # Dependencies come from the shared ServerContext the lifespan
        # populates (fastmcp 3.x offers no get_state on the server).
        result = await memory_search(
            project=project,
            query=query,
            payload_types=payload_types,
            domain_tags=domain_tags,
            token_budget=token_budget,
            include_superseded=include_superseded,
            search_callable=None,  # Use real search
            context=context,
            allowed_projects=allowed_projects,
        )

        # Return the result (already wrapped by @tool_safe)
        return result

    # The ranked results one by one, for clients that score each result
    # themselves and hold no database address (a build sandbox).
    @mcp.tool(name="memory_search_items")
    async def memory_search_items_tool(
        project: str,
        query: str | None = None,
        payload_types: list[str] | None = None,
        domain_tags: list[str] | None = None,
        token_budget: int | None = None,
        include_superseded: bool = False,
        require_substantive: bool = False,
    ) -> dict[str, Any]:
        """Search fleet-memory and return the ranked results one by one.

        Args:
            project: Project identifier (underscores only, no hyphens)
            query: Search query string (optional if filters provided)
            payload_types: Filter by payload types (empty = all types)
            domain_tags: Filter by domain tags (empty = no tag filter)
            token_budget: Accepted for parity with memory_search; nothing is assembled
            include_superseded: Include superseded memories (default: False)
            require_substantive: Drop records with no usable prose (default: False)

        Returns:
            Dict with ``items``: each ``{"value": {"natural_key", "content"}, "score"}``,
            in ranked order
        """
        return await memory_search_items(
            project=project,
            query=query,
            payload_types=payload_types,
            domain_tags=domain_tags,
            token_budget=token_budget,
            include_superseded=include_superseded,
            require_substantive=require_substantive,
            search_callable=None,
            context=context,
            allowed_projects=allowed_projects,
        )
