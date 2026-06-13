# FEAT-MEM-05 — Retrieval API + Context Assembly

Read-path counterpart to the deterministic writer (FEAT-MEM-03). A single
service entry point performs a filtered, vector-ranked, token-budgeted search
over typed fleet-memory records and assembles one context block:

```
search(project, payload_types, domain_tags, query, token_budget, include_superseded=False)
```

It excludes superseded records by default, ports guardkit's job-specific
context composition by complexity band, reports a coverage score, and ships a
probe-set evaluation harness behind the ≥15-query retrieval-parity gate (AC-3).

- **Plan / review:** TASK-REV-RA05 · `.claude/reviews/TASK-REV-RA05-review-report.md`
- **Spec:** `features/retrieval-api/` (31 scenarios, 9 assumptions)
- **Feature file:** `.guardkit/features/FEAT-MEM-05.yaml`
- **Build:** `/feature-build FEAT-MEM-05`

## Acceptance Criteria (FEAT-MEM-05)

- AC-1 — Budgeted assembly never exceeds the token budget (tiktoken-measured).
- AC-2 — Superseded records excluded by default, includable by flag.
- AC-3 — Probe-set harness runs ≥15 fixed queries and emits a parity report vs
  recorded Graphiti answers.
- (Out of scope) p95 < 200ms latency — a performance gate for the probe
  harness, not a behavioural scenario.

## Tasks

| ID | Task | Type | Cx | Wave | Deps |
|----|------|------|----|------|------|
| TASK-RA-001 | SearchRequest model and validation | declarative | 4 | 1 | — |
| TASK-RA-002 | Filtered vector search core | feature | 7 | 2 | 001 |
| TASK-RA-003 | Token-budgeted assembly + coverage | feature | 6 | 3 | 002 |
| TASK-RA-004 | Job-specific composition by band | feature | 6 | 4 | 003 |
| TASK-RA-005 | Probe-set parity harness | feature | 6 | 4 | 003 |
| TASK-RA-006 | Unit / security / concurrency tests | testing | 4 | 5 | 004, 005 |
| TASK-RA-007 | Integration tests (real store + embed) | testing | 4 | 5 | 004, 005 |

## Open assumptions to verify (low confidence)

- ASSUM-001 — complexity bands `simple`/`standard`/`complex` (verify against
  guardkit's actual builder before FEAT-MEM-08 cutover).
- ASSUM-007 — parity gate passes on zero divergence (named constant; OD-2 may
  pick a tolerance).
- ASSUM-008 — a request with neither query nor filter is rejected.
- ASSUM-009 — a memory larger than the whole budget is omitted whole.
