# Feature Spec Summary: Memory Storage Substrate

**Feature**: FEAT-MEM-01 (Phase CORE build plan)
**Stack**: python
**Generated**: 2026-06-12T15:19:41Z
**Scenarios**: 34 total (6 smoke, 0 regression; 3 scenario outlines covering 9 example rows)
**Assumptions**: 13 total (4 high / 6 medium / 3 low confidence)
**Review required**: Yes — 3 low-confidence values were human-confirmed as placeholders at spec time; verify during planning/implementation

## Scope

The storage substrate for fleet-memory: LangGraph `AsyncPostgresStore` on Postgres 16 + pgvector, with a 768-dimension nomic-embed-text-v1.5 embed function served by llama-swap on GB10 (:9000). Two deployment targets — `deploy/local/` provides an ephemeral, random-port, throwaway instance used by ALL automated test gates (including AutoBuild), and `deploy/nas/` provides the durable shared instance on the Synology NAS (backed-up volume, port 5432 exposed to LAN/Tailscale only). The specification covers store semantics (put/get/delete/semantic search with metadata filters), the lifespan-managed connection pool, pydantic-settings profile configuration, and the three-tier test strategy (fake-embed unit tests, marker-gated integration tests against the ephemeral instance, one documented smoke against the NAS productizing runbook gates G2–G5).

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 12 |
| Boundary conditions (@boundary) | 5 |
| Negative cases (@negative, primary) | 6 |
| Edge cases (@edge-case) | 11 |

`@negative` additionally appears on 2 scenarios whose primary category is boundary/edge (dimension mismatch, credential hygiene). `@smoke` marks the 6-scenario minimal set: key round-trip, ranked search, lifespan pool, ephemeral instance lifecycle, NAS-off hermeticity, zero-network unit gates.

## Deferred Items

None — all four proposal groups and all five expansion scenarios were accepted.

A production/GB10 runtime profile for configuration was intentionally **not specified** here; it is deferred to FEAT-MEM-04 per build-plan open decision OD-5 (recorded in ASSUM-001).

## Open Assumptions (low confidence)

These were accepted as placeholders by the human during spec review and need verification during `/feature-plan` or implementation:

- **ASSUM-004** — Connection pool capacity is 10; operations beyond capacity queue rather than fail
- **ASSUM-006** — Startup fail-fast surfaces within 10 seconds when the database is unreachable
- **ASSUM-008** — Embedding calls are bounded at 10 seconds

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md

The build plan's prefilled command (`/feature-plan FEAT-XXXX`) applies once a GuardKit feature id is assigned. Feature-plan Step 11 will link these scenarios to tasks via `@task:<TASK-ID>` tags — do not hand-tag ahead of that.
