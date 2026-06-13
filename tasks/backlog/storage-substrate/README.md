# Feature: Memory Storage Substrate (FEAT-CA81 / FEAT-MEM-01)

The storage substrate for fleet-memory: LangGraph `AsyncPostgresStore` on
Postgres 16 + pgvector with a 768-dimension nomic-embed-text-v1.5 embed function
served by llama-swap on GB10 (:9000).

## Problem

Phase CORE replaces Graphiti as the fleet's development-knowledge memory.
Everything downstream (typed registry, deterministic writer, relay consumer,
retrieval, MCP server — FEAT-MEM-02..09) sits on this substrate. The repo starts
from zero Python; this feature lands the package, the store, the configuration,
the dual deployment topology, and the three-tier test strategy.

## Solution approach

- **Hermetic first** (the chosen trade-off): `deploy/local/` ephemeral compose —
  UUID-named project, random port, throwaway volume — backs ALL automated gates.
  The full suite passes with the NAS powered off; AutoBuild never touches the NAS.
- **Durable second**: `deploy/nas/` compose + `deploy.sh` + `smoke.sh` productized
  from the runbook (gates G2–G5); executed by the operator, not by AutoBuild
  (TASK-MEM-008 is `operator_handoff`).
- **Store core**: settings (`FLEET_MEMORY_` prefix) → httpx embed callable
  (768-dim guard, bounded timeout) → `async_store_context` factory →
  FastStream app shell with lifespan wiring (no subscribers until FEAT-MEM-04).
- **Three test tiers**: fake-embed unit tests (no network, no DB), marker-gated
  integration tests (ephemeral Postgres + real nomic over Tailscale), one
  documented NAS smoke (operator).

## Subtasks

| ID | Title | Type | Cx | Wave |
|---|---|---|---|---|
| TASK-MEM-001 | Scaffold project layout | scaffolding | 3 | 1 |
| TASK-MEM-002 | Settings class and env profiles | declarative | 3 | 2 |
| TASK-MEM-003 | Embed callable with dimension guard | feature | 4 | 3 |
| TASK-MEM-004 | Local ephemeral compose and fixtures | infrastructure | 5 | 2 |
| TASK-MEM-005 | Store factory and namespace validation | feature | 5 | 4 |
| TASK-MEM-006 | App shell with lifespan-managed store | feature | 4 | 5 |
| TASK-MEM-007 | NAS deploy files | infrastructure | 4 | 3 |
| TASK-MEM-008 | NAS deploy execution (operator) | operator_handoff | 1 | 4 |
| TASK-MEM-009 | Unit test suite completion | testing | 4 | 6 |
| TASK-MEM-010 | Integration: store semantics + pool | testing | 6 | 6 |
| TASK-MEM-011 | Integration: boundaries + embed failures | testing | 5 | 7 |
| TASK-MEM-012 | Integration: metadata + concurrency | testing | 5 | 7 |
| TASK-MEM-013 | Assumption verification record | documentation | 1 | 8 |

## Key references

- [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md) — diagrams, contracts, waves
- [Review report](../../../.claude/reviews/TASK-REV-CA81-review-report.md) — options analysis
- `features/storage-substrate/storage-substrate.feature` — 34 BDD scenarios (tagged `@task:` by feature-plan Step 11)
- `docs/runbooks/RUNBOOK-nas-postgres-deploy.md` — NAS deploy source of truth
- `docs/research/ideas/phase-core-build-plan.md` §FEAT-MEM-01

## Acceptance criteria (build plan)

- [ ] `store.aput` / `asearch` round-trip with real nomic embeddings against the ephemeral instance
- [ ] Full test suite passes on the MacBook with the NAS powered off
- [ ] NAS deployed via `deploy.sh`; `smoke.sh` (G2–G5) passes from the Mac
- [ ] Vector index at 768 dims; similarity search with metadata filter
- [ ] No hyphens in any Postgres identifier; underscores in namespace tuples
- [ ] Pool opens/closes cleanly under lifespan; settings via env only
