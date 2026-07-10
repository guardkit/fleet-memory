"""Chronicler batch harvester (WS4-S7).

An episode harvester over the durable memory store (the materialized record of
``memory.episode.>``) that feeds two DF-008-split consumers:

  (i)  flywheel-tagged **dataset rows** (ShareGPT JSONL) into the agentic-dataset-factory
       intake — PRIVATE, Coach-validated before joining any training set; and
  (ii) draft **story-card markdown** into a human review queue — the ONLY Chronicler
       output that can ever cross the publication boundary, and only through the human
       gate, each card carrying a confidentiality flag from its project scope (DF-008).

v1 is a batch job, not a resident service (WS4 §4.2 — the relay's operational record
argues against another resident consumer before WS5's relay monitoring lands). It reads
the durable store rather than adding a second live stream consumer; the store is the
relay's materialized output of every episode.

Layering (nats-handler-service-separation discipline): ``harvest`` is PURE (no store, no
IO); ``store_source`` is the store-reading seam; ``sink`` writes the two outputs; ``run``
orchestrates. ``scripts/chronicler_harvest.py`` is the scheduled CLI entrypoint.
"""

from __future__ import annotations

from fleet_memory.chronicler.harvest import (
    HarvestedEpisode,
    HarvestResult,
    StoryCard,
    harvest,
)
from fleet_memory.chronicler.run import ChroniclerRunResult, run_chronicler

__all__ = [
    "ChroniclerRunResult",
    "HarvestResult",
    "HarvestedEpisode",
    "StoryCard",
    "harvest",
    "run_chronicler",
]
