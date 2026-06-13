# Feature Spec Summary: Deterministic Writer

**Stack**: python
**Generated**: 2026-06-13T10:20:27Z
**Scenarios**: 29 total (13 smoke, 4 regression)
**Assumptions**: 10 total (3 high / 5 medium / 2 low confidence)
**Review required**: Yes

## Scope

The deterministic writer (FEAT-MEM-03) turns a typed payload from the registry
(FEAT-MEM-02) into `AsyncPostgresStore` records with zero language-model calls.
It covers stable record identity (UUIDv5 from the natural key), content-hash
upsert semantics (same key + same content = no-op; same key + new content =
versioned update), declared supersession linking (mark predecessor
`superseded_by`, exclude from default retrieval), embed-on-write, and
per-project namespaces `("fleet_memory", project, payload_type)`. Idempotency
and supersession are the two test suites the build plan calls for; the
zero-LLM guarantee is expressed as an enforceable negative.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 8 |
| Boundary conditions (@boundary) | 4 |
| Negative cases (@negative) | 9 |
| Edge cases (@edge-case) | 15 |

(Tags overlap: several scenarios carry both @edge-case and @negative, or
@boundary and @negative; the column counts every tag occurrence.)

## Deferred Items

None. All four proposal groups and the 6-scenario expansion group were accepted.

## Open Assumptions (low confidence)

These two require human verification before the spec is treated as settled
(REVIEW REQUIRED):

- **ASSUM-008** — Forward supersession: declaring a supersession of a
  not-yet-written key succeeds and is applied when that key later appears.
  Alternative design: reject the write, or drop the dangling link silently.
- **ASSUM-010** — Batch write behaviour: one record per distinct natural key.
  Partial-batch failure mode (all-or-nothing vs per-item) is unspecified.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Deterministic Writer" \
      --context features/deterministic-writer/deterministic-writer_summary.md

Note: `@task:<TASK-ID>` tags are intentionally absent — `/feature-plan`
Step 11 links scenarios to the tasks it creates.
