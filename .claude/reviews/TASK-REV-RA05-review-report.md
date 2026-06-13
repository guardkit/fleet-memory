# Review Report: Plan Retrieval API + Context Assembly (TASK-REV-RA05)

- **Feature**: FEAT-MEM-05 — Retrieval API + Context Assembly
- **Mode**: decision · **Depth**: standard
- **Context**: features/retrieval-api/retrieval-api_summary.md (+ .feature, assumptions)
- **Decision**: Implement (structure generated)

## Context A (review scope)

- Focus: all aspects.
- Trade-off priority: quality/reliability — this is a read path FEAT-MEM-06/07/08
  depend on; correctness of budgeting, supersession, and parity is paramount.

## Context B (implementation preferences)

- Approach: Option 1 — layered service (validate → search → assemble → compose),
  probe-set harness in-feature so AC-3 is satisfiable here.
- Execution: auto-detected waves.
- Testing depth: Standard + seam tests (seam stubs at each cross-task contract).
- Parity gate (ASSUM-007): zero-divergence implemented as a single named
  constant so an OD-2 tolerance is a one-line change.

## Analysis

The spec is mature (31 scenarios; AC-1/2/3 defined). The four open low-confidence
assumptions already have provisional decisions in the `.feature`. This is the
read counterpart to two landed contracts:

- **Store (FEAT-MEM-01):** `AsyncPostgresStore` via `async_store_context`,
  namespace `("fleet_memory", project, payload_type)`, pgvector cosine,
  embed-on-write through the index config (768-dim nomic at :9000).
- **Payloads/Writer (FEAT-MEM-02/03):** `PAYLOAD_REGISTRY` (seven canonical
  types: adr, review_report, build_outcome, pattern, warning, seed_module,
  document); supersession links/state written by the deterministic writer.

There is no major architectural fork — layering, underscores-only identifiers,
and fake-embed-unit / marker-gated-integration testing are fixed by convention.
The real design content is the decomposition and four sub-decisions (bands,
parity tolerance, empty-request rejection, oversize-memory omission).

## Options considered

- **Option 1 (chosen):** layered service, 7 tasks, harness in-feature. Each
  correctness gate isolated to one task; harness reusable by MEM-07/08.
- **Option 2 (rejected):** monolithic `retrieval.py`. One oversized task carrying
  ranking + tiktoken + composition is hard to gate; fails the quality priority.
- **Option 3 (rejected):** defer composition + harness. AC-3 is the acceptance
  instrument for the whole feature — deferring it leaves MEM-05 unverifiable.

## Risks

- **R1 — tiktoken budget exactness (AC-1).** Boundary ACs hold only if the
  *assembled* block is re-measured, not summed per-memory. Isolated to RA-003.
- **R2 — composition bands (ASSUM-001, low conf).** Verify against guardkit's
  real builder before FEAT-MEM-08 cutover; carried, not blocking.
- **R3 — parity tolerance (ASSUM-007, low conf).** Named constant in RA-005.
- **R4 — supersede-mid-search / determinism.** Regression scenarios in RA-006.

## Decomposition

7 tasks, 5 waves: SearchRequest+validation → vector search core → budgeted
assembly+coverage → (job-band composition ‖ probe-set harness) → (unit/security/
concurrency tests ‖ integration tests). See IMPLEMENTATION-GUIDE.md for the data
flow / integration-contract / dependency diagrams and §4 contracts.
