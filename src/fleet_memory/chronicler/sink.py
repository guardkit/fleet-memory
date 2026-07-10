"""Output sink for the Chronicler — writes the two DF-008-split artifacts.

Dataset rows are appended as ShareGPT JSONL into the factory-intake directory (PRIVATE,
Coach-gated downstream). Story cards are written as individual markdown files into the
human-review-queue directory (the only output that may later cross the publication
boundary — never auto-published; the frontmatter carries ``published: false``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fleet_memory.chronicler.harvest import StoryCard


def write_dataset_rows(
    rows: list[dict[str, Any]], intake_dir: str, run_id: str
) -> Path | None:
    """Write flywheel dataset rows as a JSONL file into the factory intake dir.

    Args:
        rows: ShareGPT rows to write.
        intake_dir: Target intake directory (created if absent).
        run_id: Identifier for this harvest run (used in the filename).

    Returns:
        The written file path, or None if there were no rows.
    """
    if not rows:
        return None
    directory = Path(intake_dir)
    directory.mkdir(parents=True, exist_ok=True)
    out_path = directory / f"flywheel-{run_id}.jsonl"
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    return out_path


def write_story_cards(cards: list[StoryCard], queue_dir: str) -> list[Path]:
    """Write draft story cards as markdown into the human review queue dir.

    One file per story (``<slug>.md``, overwritten idempotently per story key).

    Args:
        cards: Story cards to write.
        queue_dir: Target human-review-queue directory (created if absent).

    Returns:
        The list of written file paths.
    """
    if not cards:
        return []
    directory = Path(queue_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for card in cards:
        out_path = directory / f"{card.slug}.md"
        out_path.write_text(card.render_markdown(), encoding="utf-8")
        written.append(out_path)
    return written
