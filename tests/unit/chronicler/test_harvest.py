"""Unit tests for the Chronicler pure harvest logic (no store, no IO)."""

from __future__ import annotations

from fleet_memory.chronicler.harvest import (
    CONFIDENTIAL,
    FLYWHEEL_SOURCE,
    PUBLIC,
    HarvestedEpisode,
    harvest,
)


def _build_outcome(**payload_overrides: object) -> HarvestedEpisode:
    payload = {
        "status": "success",
        "duration_seconds": 42,
        "task_id": "TASK-1",
        "correlation_id": "cid-1",
        "lessons": "Prefer explicit timeouts over defaults.",
    }
    payload.update(payload_overrides)
    return HarvestedEpisode(
        project="study_tutor",
        payload_type="build_outcome",
        natural_key="build_outcome:study_tutor:task_1",
        identifier="task_1",
        payload=payload,
        source_ref="builds/1",
        occurred_at="2026-07-07T10:00:00Z",
    )


class TestDatasetRows:
    def test_build_outcome_with_lessons_yields_flywheel_row(self) -> None:
        result = harvest([_build_outcome()])
        assert len(result.dataset_rows) == 1
        row = result.dataset_rows[0]
        assert row["metadata"]["source"] == FLYWHEEL_SOURCE
        assert row["metadata"]["flywheel"]["episode_type"] == "build_outcome"
        assert row["metadata"]["flywheel"]["natural_key"].startswith("build_outcome:")
        roles = [m["role"] for m in row["messages"]]
        assert roles == ["system", "user", "assistant"]
        assert "Lessons:" in row["messages"][-1]["content"]

    def test_build_outcome_without_lessons_yields_no_row_but_a_card(self) -> None:
        ep = _build_outcome(lessons=None, approach=None)
        result = harvest([ep])
        assert result.dataset_rows == []
        assert len(result.story_cards) == 1  # still chronicled

    def test_planning_outcome_modified_assumption_yields_refinement_row(self) -> None:
        ep = HarvestedEpisode(
            project="study_tutor",
            payload_type="planning_outcome",
            natural_key="planning_outcome:study_tutor:cid_2",
            identifier="cid_2",
            payload={
                "correlation_id": "cid-2",
                "assumptions": [
                    {"assumption_id": "a1", "disposition": "accepted"},
                    {
                        "assumption_id": "a2",
                        "disposition": "modified",
                        "text": "Users are authenticated",
                        "edit_delta": "- assume auth\n+ assume anonymous",
                    },
                ],
            },
        )
        result = harvest([ep])
        assert len(result.dataset_rows) == 1
        assert result.dataset_rows[0]["metadata"]["dimension"] == "assumption-refinement"
        assert result.dataset_rows[0]["metadata"]["disposition"] == "modified"


class TestStoryCards:
    def test_episodes_group_by_correlation_spine(self) -> None:
        a = _build_outcome(correlation_id="cid-shared")
        b = HarvestedEpisode(
            project="study_tutor",
            payload_type="deploy_record",
            natural_key="deploy_record:study_tutor:d1",
            identifier="d1",
            payload={"correlation_id": "cid-shared", "status": "complete"},
            occurred_at="2026-07-07T12:00:00Z",
        )
        result = harvest([a, b])
        assert len(result.story_cards) == 1
        card = result.story_cards[0]
        assert card.story_key == "cid-shared"
        assert len(card.episodes) == 2

    def test_default_confidentiality_is_confidential(self) -> None:
        result = harvest([_build_outcome()])
        assert result.story_cards[0].confidentiality == CONFIDENTIAL

    def test_public_project_allowlisted(self) -> None:
        result = harvest([_build_outcome()], public_projects={"study_tutor"})
        assert result.story_cards[0].confidentiality == PUBLIC
        assert result.dataset_rows[0]["metadata"]["flywheel"]["confidentiality"] == PUBLIC

    def test_card_markdown_carries_human_gate_and_confidentiality(self) -> None:
        card = harvest([_build_outcome()]).story_cards[0]
        md = card.render_markdown()
        assert "published: false" in md
        assert "confidentiality: confidential" in md
        assert "pending human review" in md
        assert "build_outcome" in md


class TestAcceptanceGate:
    def test_one_pass_over_real_shaped_events_meets_gate(self) -> None:
        # A build_outcome with lessons → ≥1 dataset row + ≥1 story card in one pass.
        result = harvest([_build_outcome()])
        assert len(result.dataset_rows) >= 1
        assert len(result.story_cards) >= 1
