"""Seed DECISION-DF-006 into fleet-memory (Postgres/pgvector on the NAS).

One-off seeder for the "frontier is a revocable teacher" decision. Uses the same
store wiring as the app (``async_store_context`` + ``DeterministicWriter``), so it
embeds-on-write through the configured embed endpoint and upserts idempotently by
content hash — safe to re-run (a second run with identical content is a no-op).

RUN FROM a node with connectivity to BOTH the NAS Postgres (``FLEET_MEMORY_PG_DSN``)
and the embed endpoint (``FLEET_MEMORY_EMBED_URL``) — i.e. the Mac over Tailscale,
or the GB10. It reads the repo's existing ``.env`` (the same one the relay/app use),
so if the relay can write, this can.

    cd ~/Projects/appmilla_github/fleet-memory
    uv run python scripts/seed_df006.py
    # or: .venv/bin/python scripts/seed_df006.py

Produces natural key:  adr:guardkit:DECISION_DF_006

Editable knobs are the UPPER_CASE constants below. `PROJECT` matches where the ADR
file lives (guardkit/docs/decisions/); change it if your convention seeds
cross-cutting DF decisions under a fleet-wide project. `DOMAIN_TAGS` drive
group-scoped reads — adjust to match the tags your other DF-00x records use.
"""

from __future__ import annotations

import asyncio

from fleet_memory.payloads.models import ADRPayload
from fleet_memory.settings import Settings
from fleet_memory.store import async_store_context
from fleet_memory.writer.core import DeterministicWriter

# --- editable knobs -------------------------------------------------------
PROJECT = "guardkit"  # underscores-only; matches the ADR file's repo
IDENTIFIER = "DECISION_DF_006"  # underscores-only (no hyphens/colons)
STATUS = "accepted"
SOURCE_REF = (
    "guardkit/docs/decisions/"
    "DECISION-DF-006-frontier-is-a-revocable-teacher-not-a-critical-path-worker.md"
)
DOMAIN_TAGS = ["decisions", "dark_factory", "inference", "frontier"]

DECISION = (
    "Frontier models are treated as revocable and volatile: no unattended, autonomous, "
    "scheduled, or continuous workload may depend on a frontier model being reachable. "
    "Frontier is retained in exactly two availability-robust roles — (1) attended planning, "
    "where a human is present to absorb its absence by waiting or falling back to local, and "
    "(2) a one-time eval/calibration yardstick (gold traces, the QA Verifier golden calibration "
    "set) captured once while frontier is available and then used offline to train or grade "
    "local models. Every stage declares a substrate preference with a mandatory local fallback: "
    "attended planning prefers frontier but degrades to best-local; unattended build (UBS night "
    "shift, AutoBuild, QA Verifier runtime) and the meta-harness improve-loop proposer are "
    "local-only; eval/calibration uses frontier opportunistically and merely pauses when it is "
    "unavailable. Degradation contract: no code path hard-codes a frontier provider as a runtime "
    "dependency; model calls resolve through a substrate router (LiteLLM :4000 / llama-swap :9000 "
    "local; harness --model where applicable), and per DF-004 the LiteLLM front door sets both "
    "fallbacks:[] and context_window_fallbacks:[] so an unattended request can never silently "
    "escalate to cloud. Consequence: frontier availability shocks (the 15 June Max "
    "programmatic-access withdrawal-then-reversal; the Fable export-control "
    "suspension-then-restoration) change the rate of model improvement, never the ability to "
    "ship. Extends DF-001 (which excludes cloud from the critical path on cost grounds) to the "
    "availability dimension; companion to DF-003 (attended/unattended boundary) and DF-004 "
    "(serving topology; the enforcement point for the no-cloud-fallback guard). Full ADR at "
    "SOURCE_REF."
)
# --------------------------------------------------------------------------


async def main() -> None:
    settings = Settings()  # loads FLEET_MEMORY_* from .env (NAS DSN + embed URL)
    payload = ADRPayload(
        project=PROJECT,
        identifier=IDENTIFIER,
        decision=DECISION,
        status=STATUS,
        source_ref=SOURCE_REF,
        domain_tags=DOMAIN_TAGS,
    )
    async with async_store_context(settings) as store:
        writer = DeterministicWriter(store=store, settings=settings)
        await writer.write(payload)
    print(f"seeded {payload.natural_key} (status={STATUS}, source_ref={SOURCE_REF})")


if __name__ == "__main__":
    asyncio.run(main())
