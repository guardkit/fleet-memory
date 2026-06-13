# Re-index Pipeline (FEAT-MEM-07)

Re-index guardkit's authoritative markdown corpus into typed payloads, published
through the live relay into the deterministic writer, with a reviewed backfill
staging gate for Fable-authored payloads.

- **Review:** TASK-REV-RIP7
- **Feature:** FEAT-MEM-07
- **Spec:** [re-index-pipeline.feature](../../../features/re-index-pipeline/re-index-pipeline.feature) · [summary](../../../features/re-index-pipeline/re-index-pipeline_summary.md)
- **Guide:** [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md)
- **Review-gate decision:** Option 1 — operator-controlled **sidecar marker** (ASSUM-003)

## Tasks

| ID | Task | Type | Wave | cx |
|---|---|---|---|---|
| RIP-001 | Reindex package + path-safe corpus walker | feature | 1 | 4 |
| RIP-002 | Episode publisher helper (json + payload_type) | feature | 1 | 5 |
| RIP-003 | Front-matter reader + classifier + parser dispatch | feature | 2 | 5 |
| RIP-004 | Deterministic typed parsers | feature | 3 | 6 |
| RIP-005 | Re-index orchestrator + run-report accounting | feature | 4 | 6 |
| RIP-006 | Backfill staging + sidecar review-gate | feature | 5 | 5 |
| RIP-007 | Stream-vs-store audit script (100% accounted) | feature | 5 | 5 |
| RIP-008 | Probe-set parity report generator | feature | 5 | 5 |
| RIP-009 | Re-index CLI entrypoint (fail-loud, resumable) | feature | 6 | 4 |
| RIP-010 | Integration tests — idempotency/concurrency/resilience/injection | testing | 7 | 6 |
| RIP-011 | **Operator run:** full-corpus verification (< 5 min, zero-LLM, idempotent, audit, parity) | operator_handoff | 8 | 3 |

## Acceptance criteria coverage

| FEAT-MEM-07 AC | Covered by |
|---|---|
| Full re-index < 5 min, zero-LLM, idempotent on second run | RIP-004/005 (zero-LLM, parse), RIP-010 (idempotency integration), RIP-011 (live wall-clock) |
| Backfill in `backfill/staging/`, publish only after review flag | RIP-006 (sidecar gate) |
| Stream-vs-store audit 100% accounted | RIP-007, RIP-011 (live) |
| Probe-set parity report against corpus | RIP-008, RIP-011 (live report) |

## Operator follow-up

1 task is `operator_handoff` (RIP-011) — see its `## Required operator follow-up`
block. Run post-merge against the live relay + NAS Postgres, then `/task-complete`.

## Next steps

```bash
/feature-build FEAT-MEM-07     # autonomous implementation (skips RIP-011)
```
