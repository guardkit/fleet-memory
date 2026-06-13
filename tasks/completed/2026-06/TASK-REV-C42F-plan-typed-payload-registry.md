---
id: TASK-REV-C42F
title: "Plan: Typed Payload Registry"
status: completed
created: 2026-06-13T00:00:00Z
updated: 2026-06-13T00:00:00Z
completed: 2026-06-13T00:00:00Z
outcome: "Implemented — FEAT-MEM-02 planned (Option 1); 4 tasks generated in tasks/backlog/typed-payload-registry/"
priority: high
task_type: review
tags: [planning, schema, pydantic, fleet-memory]
complexity: 0
clarification:
  context_a:
    decisions:
      focus: all
      tradeoff: balanced
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Plan: Typed Payload Registry

## Description

Decision-mode planning review for FEAT-MEM-02 (Typed Payload Registry): the
schema layer that makes fleet-memory writes deterministic. Seven Pydantic v2
payload types (ADR, ReviewReport, BuildOutcome, Pattern, Warning, SeedModule,
generic Document) sharing natural-key, declared-supersession, domain-tag, and
source-reference conventions, plus a `payload_type` → model dispatch registry
that both the deterministic writer (FEAT-MEM-03) and the relay consumer
(FEAT-MEM-04) route through.

Context file: features/typed-payload-registry/typed-payload-registry_summary.md
BDD spec: features/typed-payload-registry/typed-payload-registry.feature (29 scenarios)
Assumptions: features/typed-payload-registry/typed-payload-registry_assumptions.yaml (11, all confirmed)

## Acceptance Criteria

- [ ] Shared base conventions (natural key, supersession, domain_tags, source_ref, version) designed once and reused across all 7 types
- [ ] Natural-key format `<payload_type>:<project>:<identifier>` with underscore-only segment validation
- [ ] `payload_type` → model dispatch registry with bijective name↔model mapping
- [ ] Forward-compatible deserialization (extra fields ignored)
- [ ] Deterministic, byte-identical serialization across write surfaces
- [ ] All 29 BDD scenarios covered

## Review Findings

**Decision: [I]mplement** (Option 1).

Three approaches analysed:
1. **Shared `BasePayload` + 7 subclasses + registration-time registry** — chosen.
   DRY, preserves typed validation, matches repo conventions, extensible.
2. Mixin composition — rejected (YAGNI; all 7 types share all conventions).
3. Single generic model + `data` dict — rejected (loses per-type required-field
   validation, defeats the typed purpose).

**Outcome:** feature structure generated at
`tasks/backlog/typed-payload-registry/` (4 tasks, sequential waves) and
`.guardkit/features/FEAT-MEM-02.yaml`. All 29 BDD scenarios tagged `@task:`
(R2 oracle active). AutoBuild ready: `/feature-build FEAT-MEM-02`.
