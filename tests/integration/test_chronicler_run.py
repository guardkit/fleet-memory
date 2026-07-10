"""Integration test: the WS4-S7 Chronicler acceptance gate over a real store.

Gate (WS4 §9 S7 row): "one scheduled run emits ≥1 dataset row + ≥1 draft story card from
real events." This test seeds REAL typed payloads through the real DeterministicWriter into
an ephemeral Postgres store, runs one Chronicler pass over it, and asserts both outputs.

Requires Docker (ephemeral_pg / store fixtures); deselected by default (`-m integration`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fleet_memory.chronicler.run import run_chronicler
from fleet_memory.embed import make_fake_embed
from fleet_memory.payloads.models import BuildOutcomePayload
from fleet_memory.store import async_store_context
from fleet_memory.writer.core import DeterministicWriter

pytestmark = pytest.mark.integration


async def test_one_run_emits_dataset_row_and_story_card(
    test_settings, tmp_path: Path
) -> None:
    """A single harvest pass over real seeded episodes meets the S7 acceptance gate."""
    settings = test_settings.model_copy(
        update={
            "chronicler_dataset_intake_dir": str(tmp_path / "intake"),
            "chronicler_story_card_queue_dir": str(tmp_path / "queue"),
            "chronicler_public_projects": "",
        }
    )
    fake_embed = make_fake_embed(dims=settings.embed_dims)

    async with async_store_context(settings, embed_fn=fake_embed) as store:
        writer = DeterministicWriter(store=store, settings=settings)

        # Seed a REAL build_outcome carrying a lesson (→ a flywheel dataset row) plus a
        # second episode on the same task (→ a richer story card), via the real writer.
        build = BuildOutcomePayload(
            project="chronicler_itest",
            identifier="task_alpha",
            source_ref="builds/alpha",
            status="success",
            duration_seconds=42,
            task_id="TASK-ALPHA",
            lessons="Prefer explicit connect timeouts over pool defaults.",
            approach="Bound the pool-open with asyncio.timeout.",
        )
        meta = {
            "episode_type": "build_outcome",
            "name": None,
            "source": "forge.build",
            "occurred_at": "2026-07-07T10:00:00Z",
            "published_at": "2026-07-07T10:00:01Z",
            "ingest_hints": None,
            "payload_type": "build_outcome",
            "source_ref": "builds/alpha",
        }
        await writer.write(build, episode_meta=meta)

        result = await run_chronicler(store, settings, run_id="itest")

    # The acceptance gate.
    assert result.meets_acceptance(), result.as_dict()
    assert result.dataset_row_count >= 1
    assert result.story_card_count >= 1

    # The dataset row landed in the intake dir, flywheel-tagged and PRIVATE.
    assert result.dataset_path is not None
    dataset_file = Path(result.dataset_path)
    assert dataset_file.exists()
    rows = [json.loads(line) for line in dataset_file.read_text().splitlines() if line]
    mine = [
        r
        for r in rows
        if r["metadata"]["flywheel"]["project"] == "chronicler_itest"
    ]
    assert mine, "expected a flywheel dataset row for the seeded project"
    assert mine[0]["metadata"]["source"] == "flywheel"
    assert mine[0]["metadata"]["flywheel"]["confidentiality"] == "confidential"

    # A draft story card landed in the human-review queue, human-gated + confidentiality.
    assert result.story_card_paths
    card_texts = [Path(p).read_text() for p in result.story_card_paths]
    seeded_card = [t for t in card_texts if "TASK-ALPHA" in t or "task_alpha" in t]
    assert seeded_card, "expected a story card for the seeded task"
    assert "published: false" in seeded_card[0]
    assert "confidentiality: confidential" in seeded_card[0]
