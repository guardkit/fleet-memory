# Review Report: Plan Deterministic Writer (TASK-REV-DW03)

- **Feature**: FEAT-MEM-03 — Deterministic Writer
- **Mode**: decision · **Depth**: standard
- **Context**: features/deterministic-writer/deterministic-writer_summary.md (+ .feature, assumptions)
- **Decision**: Implement (structure generated)

## Context A (review scope)

- Focus: all aspects, weighted to correctness/integrity.
- Trade-off priority: hermetic correctness — unit suite needs no infrastructure;
  integration suite is marker-gated; AutoBuild never calls an LLM.

## Context B (implementation preferences)

- Approach: UUIDv5 identity + content-hash upsert; supersession as a dict update;
  embed-on-write via store index config; zero LLM by construction.
- Testing depth: Standard + seam tests.
- MEM-02 dependency: assume merged; prominent prerequisite note (no guard task).
- Execution: auto-detected waves.

## Analysis

The spec is fully settled — all 10 assumptions confirmed, including the two
REVIEW-REQUIRED low-confidence ones (ASSUM-008 forward supersession succeeds and
is applied on later appearance; ASSUM-010 one record per distinct natural key).
There is no genuine design fork; the work is a decomposition of a deterministic
service over two existing contracts:

- **Input** (FEAT-MEM-02): `BasePayload` / `PAYLOAD_REGISTRY`; natural key
  `<payload_type>:<project>:<identifier>`; `supersedes: list[str]`; `version: int`.
- **Output** (FEAT-MEM-01): `AsyncPostgresStore` via `async_store_context`;
  namespace `("fleet_memory", project, payload_type)`; embed-on-write through the
  index config (`fields=["content"]`).

The thesis — zero LLM on the structured write path — is expressed as an
enforceable negative (DW-004 import test). The only external model is the
embedding service, which is not a language model.

## Risks

- **R1 — MEM-02 not yet merged.** Mitigated by the prerequisite note; build must
  not start until `fleet_memory.payloads` is on `main`.
- **R2 — embed-on-write atomicity.** Embed failure / dimension mismatch / db
  outage must leave no partial record (ASSUM-009). Covered by DW-002 ACs and
  DW-004 failure-mode tests.
- **R3 — supersession composition.** Chains, forward links, cross-project, and
  racing successors are the highest-complexity area; isolated in DW-003 with a
  dedicated suite (DW-005) and a feature-level smoke gate after Wave 3.

## Decomposition

5 tasks, 4 waves: identity/hash → writer core → (supersession ‖ idempotency+zero-LLM
tests) → supersession tests. See IMPLEMENTATION-GUIDE.md for diagrams and §4
integration contracts.
