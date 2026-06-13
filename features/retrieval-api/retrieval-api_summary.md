# Feature Spec Summary: Retrieval API + Context Assembly

**Stack**: python
**Generated**: 2026-06-13T11:46:58Z
**Scenarios**: 31 total (10 smoke, 6 regression)
**Assumptions**: 9 total (3 high / 2 medium / 4 low confidence)
**Review required**: Yes

## Scope

Covers the FEAT-MEM-05 retrieval surface: a filtered, vector-ranked, token-budgeted
`search(project, payload_types, domain_tags, query, token_budget, include_superseded=False)`
that assembles a single context block, excludes superseded records by default, ports
guardkit's job-specific context composition by complexity band, and reports a coverage
score. Also covers the probe-set evaluation harness behind the ≥15-query retrieval-parity
gate, including divergence flagging against recorded Graphiti baselines.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 8 |
| Boundary conditions (@boundary) | 6 |
| Negative cases (@negative) | 11 |
| Edge cases (@edge-case) | 12 |

(Tags overlap: several boundary and edge-case scenarios are also tagged `@negative`.)

## Deferred Items

None — all four proposed groups and all six edge-case-expansion scenarios were accepted.

Out of scope by upstream decision: `related_keys` one-hop link expansion (deferred to the
writer/retrieval boundary per the typed-payload-registry spec) and the p95 < 200ms latency
AC (a performance gate measured by the probe harness, not a behavioural scenario).

## Open Assumptions (low confidence)

These four need human verification before the spec is treated as settled:

- **ASSUM-001** — complexity bands `simple`/`standard`/`complex` (verify against guardkit's
  actual job-specific context builder before FEAT-MEM-08 cutover).
- **ASSUM-007** — parity gate passes only on zero divergence (depends on the OD-2 probe-set
  freeze; a tolerance threshold may be chosen instead).
- **ASSUM-008** — a request with neither query nor filter is rejected (project-only listing
  may be a legitimate API shape).
- **ASSUM-009** — a memory larger than the whole budget is omitted whole, not truncated.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Retrieval API + Context Assembly" \
      --context features/retrieval-api/retrieval-api_summary.md

`/feature-plan` Step 11 will link these scenarios to the tasks it creates by inserting
`@task:<TASK-ID>` tags; none are present yet (feature-spec is link-free by design).
