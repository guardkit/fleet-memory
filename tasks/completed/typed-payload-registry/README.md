# Feature: Typed Payload Registry (FEAT-MEM-02)

The schema layer that makes fleet-memory writes deterministic. Seven Pydantic v2
payload types — ADR, ReviewReport, BuildOutcome, Pattern, Warning, SeedModule,
and a generic Document — share a natural-key, declared-supersession, domain-tag,
and source-reference convention, plus a `payload_type` → model dispatch registry
that the deterministic writer (FEAT-MEM-03) and relay consumer (FEAT-MEM-04)
both route through.

## Why

- **Dedup is a key lookup** — identical type/project/identifier → one natural key.
- **Supersession is a declared fact**, not an inferred LLM judgement (RD-6).
- **Writes are deterministic** — same payload in → byte-identical store form out.

## Planning provenance

- **Review:** TASK-REV-C42F (decision mode; focus=all, trade-off=balanced)
- **Approach:** Option 1 — shared `BasePayload` + 7 subclasses + registry
- **Spec:** `features/typed-payload-registry/typed-payload-registry.feature` (29 scenarios)
- **Assumptions:** `features/typed-payload-registry/typed-payload-registry_assumptions.yaml` (11, all confirmed)

## Tasks

| ID | Title | Type | Cx | Wave | Deps |
|----|-------|------|----|------|------|
| TASK-TPR-001 | Payload base conventions and validators | declarative | 6 | 1 | — |
| TASK-TPR-002 | Seven concrete payload types | declarative | 4 | 2 | TASK-TPR-001 |
| TASK-TPR-003 | Payload dispatch registry and round-trip | feature | 5 | 3 | TASK-TPR-002 |
| TASK-TPR-004 | BDD scenario suite (29 scenarios) | testing | 4 | 4 | TASK-TPR-003 |

Execution is a sequential chain — see `IMPLEMENTATION-GUIDE.md` for the data
flow, integration-contract, and dependency diagrams.

## Next steps

```bash
# Review the guide and diagrams
open tasks/backlog/typed-payload-registry/IMPLEMENTATION-GUIDE.md

# Implement sequentially
/task-work TASK-TPR-001
/task-work TASK-TPR-002
/task-work TASK-TPR-003
/task-work TASK-TPR-004

# Or autonomously via AutoBuild
/feature-build FEAT-MEM-02
```
