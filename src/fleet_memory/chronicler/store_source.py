"""Store-reading seam for the Chronicler (the only store-aware harvest module).

Reads every typed episode record out of the durable store — the materialized record of
``memory.episode.>`` — and rehydrates each into a pure ``HarvestedEpisode``. Prose/chunk
records (no ``payload_type``) are skipped: the Chronicler harvests typed episodes only.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fleet_memory.chronicler.harvest import HarvestedEpisode

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore


def _rehydrate(namespace: tuple[str, ...], value: dict[str, Any]) -> HarvestedEpisode | None:
    """Rebuild a HarvestedEpisode from a stored record value, or None to skip it."""
    # Typed episodes always carry payload_type (writer core); chunks/prose do not.
    payload_type = value.get("payload_type")
    if not payload_type:
        return None

    content = value.get("content")
    try:
        payload = json.loads(content) if content else {}
    except (TypeError, json.JSONDecodeError):
        payload = {}

    meta = value.get("episode_meta") or {}
    project = value.get("project") or (namespace[1] if len(namespace) > 1 else "")
    return HarvestedEpisode(
        project=project,
        payload_type=payload_type,
        natural_key=value.get("natural_key", ""),
        identifier=value.get("identifier", ""),
        payload=payload,
        source_ref=meta.get("source_ref") or value.get("source_ref"),
        occurred_at=meta.get("occurred_at"),
        name=meta.get("name"),
        source=meta.get("source"),
    )


async def read_episodes(
    store: AsyncPostgresStore,
    *,
    limit: int = 1000,
    since: str | None = None,
) -> list[HarvestedEpisode]:
    """Read all typed episode records from the durable store.

    Enumerates every ``(fleet_memory, project, payload_type)`` namespace and scans each
    (no query → all items; explicit ``limit`` because the default page size is small).

    Args:
        store: The AsyncPostgresStore to read from.
        limit: Max records scanned per namespace.
        since: Optional ISO-8601 lower bound on ``occurred_at`` (inclusive-exclusive by
            string compare — ISO-8601 is lexicographically ordered); episodes with a known
            earlier ``occurred_at`` are skipped. Undated episodes are always included.

    Returns:
        The list of rehydrated episodes across all projects and types.
    """
    namespaces = await store.alist_namespaces(
        prefix=("fleet_memory",), max_depth=3, limit=limit
    )

    episodes: list[HarvestedEpisode] = []
    for namespace in namespaces:
        if len(namespace) != 3:
            continue
        items = await store.asearch(namespace, limit=limit)
        for item in items:
            episode = _rehydrate(namespace, item.value)
            if episode is None:
                continue
            if since and episode.occurred_at and episode.occurred_at < since:
                continue
            episodes.append(episode)
    return episodes
