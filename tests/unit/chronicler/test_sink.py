"""Unit tests for the Chronicler output sink (writes into tmp dirs)."""

from __future__ import annotations

import json
from pathlib import Path

from fleet_memory.chronicler.harvest import HarvestedEpisode, StoryCard, harvest
from fleet_memory.chronicler.sink import write_dataset_rows, write_story_cards


def _rows() -> list[dict]:
    ep = HarvestedEpisode(
        project="study_tutor",
        payload_type="build_outcome",
        natural_key="build_outcome:study_tutor:t1",
        identifier="t1",
        payload={"status": "success", "task_id": "t1", "lessons": "x"},
    )
    return harvest([ep]).dataset_rows


class TestWriteDatasetRows:
    def test_writes_jsonl_one_line_per_row(self, tmp_path: Path) -> None:
        rows = _rows()
        out = write_dataset_rows(rows, str(tmp_path / "intake"), "run1")
        assert out is not None and out.exists()
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == len(rows)
        parsed = json.loads(lines[0])
        assert parsed["metadata"]["source"] == "flywheel"

    def test_empty_rows_writes_nothing(self, tmp_path: Path) -> None:
        assert write_dataset_rows([], str(tmp_path / "intake"), "run1") is None


class TestWriteStoryCards:
    def test_writes_markdown_per_card(self, tmp_path: Path) -> None:
        card = StoryCard(
            story_key="cid-1",
            slug="cid_1",
            project="study_tutor",
            confidentiality="confidential",
        )
        paths = write_story_cards([card], str(tmp_path / "queue"))
        assert len(paths) == 1
        assert paths[0].name == "cid_1.md"
        assert "published: false" in paths[0].read_text(encoding="utf-8")

    def test_empty_cards_writes_nothing(self, tmp_path: Path) -> None:
        assert write_story_cards([], str(tmp_path / "queue")) == []
