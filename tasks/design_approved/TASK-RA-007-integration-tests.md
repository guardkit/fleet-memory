---
complexity: 4
dependencies:
- TASK-RA-004
- TASK-RA-005
feature_id: FEAT-MEM-05
id: TASK-RA-007
implementation_mode: task-work
parent_review: TASK-REV-RA05
status: design_approved
task_type: testing
title: Marker-gated integration tests against real store and embed
wave: 5
---

# Task: Marker-gated integration tests against real store and embed

## Description

`@pytest.mark.integration` tests that exercise the full retrieval path against
an ephemeral Postgres 16 + pgvector instance (deploy/local) with real nomic
embeddings over Tailscale. Proves the search→assembly→coverage path round-trips
against real vectors, and that the probe-set harness runs end-to-end.

## Acceptance Criteria

- [ ] Integration tests are marker-gated (`@pytest.mark.integration`) and
      excluded from the hermetic unit gate.
- [ ] A populated ephemeral store + real embed returns project-scoped,
      cosine-ranked results for a real query.
- [ ] Supersession exclusion holds end-to-end against records written by the
      deterministic writer (FEAT-MEM-03).
- [ ] Budgeted assembly stays within budget when measured against a real
      assembled block (AC-1) over real corpus content.
- [ ] The probe-set harness runs the frozen query set against the real
      (re-indexed) corpus and emits a parity report.
- [ ] Tests use a throwaway, random-port instance (no NAS dependency).

## Coach Validation

```bash
pytest tests/integration -m integration -x
```

## Implementation Notes

- Follow the FEAT-MEM-01 integration pattern: ephemeral `pgvector/pgvector:pg16`
  via `deploy/local/`, random port from env, real embed at llama-swap `:9000`
  over Tailscale.
- The p95 < 200ms latency AC is a performance gate for the probe harness, not a
  behavioural assertion here — out of scope for this feature per the spec.