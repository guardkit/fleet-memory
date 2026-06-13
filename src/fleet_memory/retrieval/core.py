"""Filtered vector search core for fleet-memory retrieval.

Implements filtered, vector-ranked retrieval over AsyncPostgresStore with:
- Project-scoped search (namespace filtering)
- Payload type filtering (0/1/many)
- Domain tag filtering
- Supersession handling (exclude by default, include if requested)
- Deterministic ordering for equal relevance scores
- Error propagation with credential hygiene

Producer: TASK-RA-002
Consumer: FEAT-MEM-05 (assembly, harness)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.store.base import SearchItem

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.retrieval.search_request import SearchRequest

# Type alias for search results
SearchResult = SearchItem


def _extract_payload_type(natural_key: str) -> str | None:
    """Extract payload type from natural key format type:project:identifier.

    Args:
        natural_key: Natural key string (e.g., "document:proj_a:1")

    Returns:
        Payload type string or None if natural_key is malformed
    """
    parts = natural_key.split(":")
    if len(parts) >= 1:
        return parts[0]
    return None


def _matches_payload_types(item: SearchItem, payload_types: list[str]) -> bool:
    """Check if search item matches requested payload types.

    Args:
        item: SearchItem to check
        payload_types: List of requested types (empty means all types)

    Returns:
        True if item matches (or no filter), False otherwise
    """
    if not payload_types:
        # Empty list means all types
        return True

    natural_key = item.value.get("natural_key", "")
    item_type = _extract_payload_type(natural_key)

    return item_type in payload_types


def _matches_domain_tags(item: SearchItem, domain_tags: list[str]) -> bool:
    """Check if search item matches requested domain tags.

    Args:
        item: SearchItem to check
        domain_tags: List of requested tags (empty means no tag filter)

    Returns:
        True if item matches (or no filter), False otherwise
    """
    if not domain_tags:
        # Empty list means no tag filter
        return True

    item_tags = item.value.get("domain_tags", [])
    # Item must have at least one of the requested tags
    return any(tag in item_tags for tag in domain_tags)


def _is_superseded(item: SearchItem) -> bool:
    """Check if search item is marked as superseded.

    Args:
        item: SearchItem to check

    Returns:
        True if item has superseded_by field, False otherwise
    """
    return "superseded_by" in item.value


def _sort_key(item: SearchItem) -> tuple[float, str]:
    """Generate sort key for deterministic ordering.

    Sort by score descending (negated for sort), then by natural_key ascending.

    Args:
        item: SearchItem to generate key for

    Returns:
        Tuple of (negated_score, natural_key) for sorting
    """
    # Negate score for descending order (higher scores first)
    score = -(item.score or 0.0)
    natural_key = item.value.get("natural_key", "")
    return (score, natural_key)


async def search(
    request: SearchRequest,
    store: AsyncPostgresStore,
) -> list[SearchResult]:
    """Execute filtered vector search over AsyncPostgresStore.

    Takes a validated SearchRequest and returns ranked memories matching all filters:
    - Project scope (via namespace)
    - Payload types (if specified)
    - Domain tags (if specified)
    - Supersession state (excluded by default)

    Results are ordered by cosine similarity descending, with deterministic
    tie-breaking on natural_key for equal scores.

    Args:
        request: Validated SearchRequest from TASK-RA-001
        store: AsyncPostgresStore instance with pgvector index

    Returns:
        List of SearchResult (SearchItem) objects, ranked by relevance

    Raises:
        EmbedServiceError: When embedding service is unavailable (no credentials)
        TimeoutError: When store is unreachable (no credentials in message)

    Example:
        >>> request = SearchRequest(project="guardkit", query="retries", token_budget=2000)
        >>> async with async_store_context(settings) as store:
        ...     results = await search(request, store)
        ...     for result in results:
        ...         print(f"{result.score}: {result.value['content']}")
    """
    # Build namespace prefix for project scope
    # Format: ("fleet_memory", project)
    namespace_prefix = ("fleet_memory", request.project)

    # Execute vector search with query
    # The store handles embedding and vector similarity via its index config
    # Any EmbedServiceError or TimeoutError will propagate with credential hygiene
    # (already enforced by embed.py and store.py)
    raw_results = await store.asearch(
        namespace_prefix,
        query=request.query,
    )

    # Apply filters
    filtered_results = raw_results

    # Filter by payload types
    filtered_results = [
        item
        for item in filtered_results
        if _matches_payload_types(item, request.payload_types)
    ]

    # Filter by domain tags
    filtered_results = [
        item
        for item in filtered_results
        if _matches_domain_tags(item, request.domain_tags)
    ]

    # Filter superseded records unless include_superseded=True
    if not request.include_superseded:
        filtered_results = [
            item for item in filtered_results if not _is_superseded(item)
        ]

    # Deduplicate by key (handle mid-search supersession consistency)
    # Keep first occurrence (which will be highest scored after sorting)
    seen_keys: set[str] = set()
    deduplicated_results = []
    for item in filtered_results:
        if item.key not in seen_keys:
            seen_keys.add(item.key)
            deduplicated_results.append(item)

    # Sort by score descending, then natural_key ascending for deterministic ordering
    sorted_results = sorted(deduplicated_results, key=_sort_key)

    return sorted_results
