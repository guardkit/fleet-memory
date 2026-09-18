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

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from langgraph.store.base import SearchItem

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.retrieval.search_request import SearchRequest

# Type alias for search results
SearchResult = SearchItem

# Preserve AsyncPostgresStore's accepted default result bound explicitly. Partitioned
# type searches merge back to this same global cap after deterministic ordering.
_RANKED_RESULT_LIMIT = 10
_LOGICAL_PAGE_SIZE = 10
_MAX_SCANNED_PER_PARTITION = 1024
_SEARCH_TIMEOUT_SECONDS = 20
logger = logging.getLogger(__name__)


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


def _matches_project(item: SearchItem, project: str) -> bool:
    """Guard against namespace-prefix bleed across sibling projects.

    ``AsyncPostgresStore.asearch(("fleet_memory", project))`` scopes via a
    ``store.prefix LIKE 'fleet_memory.{project}%'`` match. That prefix match also
    selects a sibling project whose name shares the requested project as a prefix
    (e.g. ``project="guardkit"`` bleeds ``fleet_memory.guardkit_factory.*``). Stored
    items always carry a 3-tuple namespace ``("fleet_memory", project, payload_type)``,
    so require the item's own project segment to equal the requested project exactly.

    Args:
        item: SearchItem to check
        project: Requested project (exact match required)

    Returns:
        True if the item's namespace project segment equals ``project``.
    """
    namespace = getattr(item, "namespace", None)
    if not namespace or len(namespace) < 2:
        return False
    return namespace[1] == project


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


def _item_domain_tags(item: SearchItem) -> list[str]:
    """Resolve an item's domain_tags, looking inside the embedded content if needed.

    The deterministic writer (writer/core.py) persists a record's ``domain_tags`` only
    INSIDE the embedded ``content`` JSON (``json.dumps(payload.model_dump())``), not as a
    top-level stored field. A top-level-only read therefore saw ``[]`` for every typed
    payload and any non-empty ``domain_tags`` filter deselected every such record
    (TASK-MEM08-012). Resolve from the top level first (forward-compatible if the writer
    later lifts it), then fall back to parsing ``content``. Chunk records carry prose (not
    JSON) in ``content`` and legitimately have no tags → ``[]``.
    """
    tags = item.value.get("domain_tags")
    if isinstance(tags, list):
        return tags
    content = item.value.get("content")
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return []
        if isinstance(parsed, dict):
            nested = parsed.get("domain_tags")
            if isinstance(nested, list):
                return nested
    return []


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

    item_tags = _item_domain_tags(item)
    # Item must have at least one of the requested tags
    return any(tag in item_tags for tag in domain_tags)


def _has_substantive_content(item: SearchItem) -> bool:
    """Return whether a typed outcome/document carries canonical usable content.

    This predicate is opt-in. Normal retrieval continues to return metadata-only
    records. Contextual task-outcome retrieval uses it to avoid status/tag shells
    whose approach and lessons are both blank.
    """
    content = item.value.get("content")
    if not isinstance(content, str):
        return False
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False

    payload_type = item.value.get("payload_type") or _extract_payload_type(
        item.value.get("natural_key", "")
    )
    if payload_type == "build_outcome":
        fields = (payload.get("approach"), payload.get("lessons"))
    elif payload_type == "document":
        fields = (payload.get("content"),)
    else:
        return False
    return any(isinstance(value, str) and bool(value.strip()) for value in fields)


async def _search_partition(
    request: SearchRequest,
    store: AsyncPostgresStore,
    payload_type: str | None,
) -> list[SearchResult]:
    """Return up to ten accepted results from one prefiltered type partition."""
    namespace = ("fleet_memory", request.project)
    metadata_filter: dict[str, object] = {"project": request.project}
    if payload_type is not None:
        namespace = (*namespace, payload_type)
        metadata_filter["payload_type"] = payload_type

    accepted: list[SearchResult] = []
    seen_keys: set[str] = set()
    offset = 0
    exhausted = False
    while len(accepted) < _RANKED_RESULT_LIMIT and not exhausted:
        remaining = _MAX_SCANNED_PER_PARTITION - offset
        if remaining <= 0:
            logger.error(
                "filtered search incomplete: scanned %d candidates in %s without "
                "finding %d accepted results",
                _MAX_SCANNED_PER_PARTITION,
                payload_type or "all-types",
                _RANKED_RESULT_LIMIT,
            )
            raise RuntimeError("filtered search incomplete at candidate scan bound")

        logical_size = min(_LOGICAL_PAGE_SIZE, remaining)
        # Installed langgraph-postgres expands its inner vector candidate window
        # from limit but ignores offset. Compensate with limit=offset+page size,
        # then consume exactly one logical page. A plain limit=10/offset=20
        # falsely exhausts after rank 21.
        fetched = await store.asearch(
            namespace,
            query=request.query,
            filter=metadata_filter,
            limit=offset + logical_size,
            offset=offset,
        )
        page = fetched[:logical_size]
        request_limit = offset + logical_size
        exhausted = len(fetched) < request_limit and len(fetched) <= logical_size

        for item in page:
            if not _matches_project(item, request.project):
                continue
            if payload_type is not None and not _matches_payload_types(
                item, [payload_type]
            ):
                continue
            if not _matches_domain_tags(item, request.domain_tags):
                continue
            if not request.include_superseded and _is_superseded(item):
                continue
            if request.require_substantive and not _has_substantive_content(item):
                continue
            if item.key in seen_keys:
                continue
            seen_keys.add(item.key)
            accepted.append(item)
            if len(accepted) >= _RANKED_RESULT_LIMIT:
                break

        offset += len(page)
        if len(page) < logical_size:
            exhausted = True
        if (
            offset >= _MAX_SCANNED_PER_PARTITION
            and len(accepted) < _RANKED_RESULT_LIMIT
            and not exhausted
        ):
            logger.error(
                "filtered search incomplete: scan bound reached in %s",
                payload_type or "all-types",
            )
            raise RuntimeError("filtered search incomplete at candidate scan bound")

    return accepted


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
    # Filter project/type before ranking, then page until each requested
    # partition has enough accepted candidates for the final global top ten.
    # Domain tags, supersession absence, and opt-in substantive content cannot be
    # expressed by the installed store's scalar metadata filter, so pagination
    # applies those predicates without a single arbitrary over-fetch depth.
    partitions: list[str | None] = (
        sorted(set(request.payload_types)) if request.payload_types else [None]
    )
    try:
        async with asyncio.timeout(_SEARCH_TIMEOUT_SECONDS):
            if request.require_substantive:
                partition_results = [
                    await _search_partition(request, store, payload_type)
                    for payload_type in partitions
                ]
            else:
                # Preserve the accepted single-page behavior for ordinary history
                # and metadata consumers. Pagination is an explicit contextual
                # task-outcome capability, never an implicit generic search change.
                partition_results = []
                for payload_type in partitions:
                    namespace = ("fleet_memory", request.project)
                    metadata_filter: dict[str, object] = {
                        "project": request.project
                    }
                    if payload_type is not None:
                        namespace = (*namespace, payload_type)
                        metadata_filter["payload_type"] = payload_type
                    partition_results.append(
                        await store.asearch(
                            namespace,
                            query=request.query,
                            filter=metadata_filter,
                            limit=_RANKED_RESULT_LIMIT,
                            offset=0,
                        )
                    )
    except TimeoutError:
        logger.error(
            "filtered search incomplete: exceeded %ss timeout",
            _SEARCH_TIMEOUT_SECONDS,
        )
        raise
    raw_results = [
        item for partition in partition_results for item in partition
    ]

    # Apply filters
    filtered_results = raw_results

    # Exact project scope: the store's namespace prefix is a LIKE 'prefix%' match,
    # which would bleed a sibling project sharing a name-prefix (e.g. "guardkit" vs
    # "guardkit_factory"). Require each item's namespace project segment to match
    # the requested project exactly. (FEAT-MEM-09 WS-0 multi-project hardening.)
    filtered_results = [
        item for item in filtered_results if _matches_project(item, request.project)
    ]

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

    return sorted_results[:_RANKED_RESULT_LIMIT]
