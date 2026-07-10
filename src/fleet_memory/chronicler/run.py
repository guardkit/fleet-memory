"""Chronicler run orchestrator — reads the store, harvests, writes both outputs.

One call == one scheduled harvest pass (the WS4-S7 acceptance unit: "one scheduled run
emits ≥1 dataset row + ≥1 draft story card from real events"). Stays thin: the store read
is in ``store_source``, the transform in ``harvest``, the writes in ``sink``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fleet_memory.chronicler.harvest import harvest
from fleet_memory.chronicler.sink import write_dataset_rows, write_story_cards
from fleet_memory.chronicler.store_source import read_episodes

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.settings import Settings


@dataclass
class ChroniclerRunResult:
    """Machine-readable summary of one harvest run (for the CLI's JSON output)."""

    run_id: str
    episode_count: int
    dataset_row_count: int
    story_card_count: int
    dataset_path: str | None
    story_card_paths: list[str]

    def meets_acceptance(self) -> bool:
        """WS4-S7 gate: ≥1 dataset row AND ≥1 draft story card."""
        return self.dataset_row_count >= 1 and self.story_card_count >= 1

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "episode_count": self.episode_count,
            "dataset_row_count": self.dataset_row_count,
            "story_card_count": self.story_card_count,
            "dataset_path": self.dataset_path,
            "story_card_paths": self.story_card_paths,
            "meets_acceptance": self.meets_acceptance(),
        }


def _parse_public_projects(raw: str) -> set[str]:
    """Parse the comma-separated public-projects allowlist into a set."""
    return {part.strip() for part in raw.split(",") if part.strip()}


async def run_chronicler(
    store: AsyncPostgresStore,
    settings: Settings,
    *,
    run_id: str,
    since: str | None = None,
) -> ChroniclerRunResult:
    """Run one Chronicler harvest pass over the durable store.

    Args:
        store: The AsyncPostgresStore to harvest from.
        settings: Configuration (intake/queue dirs, public-projects, scan limit).
        run_id: Identifier for this run (filenames + summary).
        since: Optional ISO-8601 ``occurred_at`` lower bound (incremental harvests).

    Returns:
        A ``ChroniclerRunResult`` summarizing what was emitted.
    """
    episodes = await read_episodes(
        store, limit=settings.chronicler_scan_limit, since=since
    )
    public_projects = _parse_public_projects(settings.chronicler_public_projects)

    result = harvest(episodes, public_projects=public_projects)

    dataset_path: Path | None = write_dataset_rows(
        result.dataset_rows, settings.chronicler_dataset_intake_dir, run_id
    )
    card_paths = write_story_cards(
        result.story_cards, settings.chronicler_story_card_queue_dir
    )

    return ChroniclerRunResult(
        run_id=run_id,
        episode_count=len(episodes),
        dataset_row_count=len(result.dataset_rows),
        story_card_count=len(result.story_cards),
        dataset_path=str(dataset_path) if dataset_path else None,
        story_card_paths=[str(p) for p in card_paths],
    )
