# Feature Spec Summary: Typed Payload Registry

**Stack**: python
**Generated**: 2026-06-13T08:36:59Z
**Scenarios**: 29 total (8 smoke, 5 regression)
**Assumptions**: 11 total (4 high / 3 medium / 4 low confidence)
**Review required**: Yes

## Scope

FEAT-MEM-02 defines the schema layer that makes fleet-memory writes deterministic:
seven Pydantic payload types (ADR, ReviewReport, BuildOutcome, Pattern, Warning,
SeedModule, and a generic Document) sharing the natural-key, declared-supersession,
domain-tag, and source-reference conventions, plus a `payload_type` → model dispatch
registry that both the deterministic writer (FEAT-MEM-03) and the relay consumer
(FEAT-MEM-04) route through. The specification covers natural-key construction and
stability, underscore-only identifier validation, supersession shape validation,
registry round-tripping, and forward-compatible deserialization.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 7 |
| Boundary conditions (@boundary) | 5 |
| Negative cases (@negative) | 8 |
| Edge cases (@edge-case) | 14 |

(Categories overlap: several scenarios carry both `@boundary`/`@edge-case` and
`@negative`. Totals above count each tag independently.)

## Deferred Items

None. All four proposed groups and all six edge-case expansion scenarios were
accepted. `related_keys` (one-hop links) was deliberately excluded from this
feature (ASSUM-008) and deferred to the retrieval/writer features.

## Open Assumptions (low confidence)

These four need human verification before the spec is treated as settled:

- **ASSUM-005** — domain_tags format (lowercase_underscore tokens, optional, default empty)
- **ASSUM-006** — version stamp is a monotonic integer beginning at 1
- **ASSUM-007** — source_ref is a required free-form provenance reference string
- **ASSUM-011** — self-supersession rejected; cross-project supersession permitted

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Typed Payload Registry" \
      --context features/typed-payload-registry/typed-payload-registry_summary.md
