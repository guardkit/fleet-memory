# Feature Spec Summary: Re-index Pipeline

**Stack**: python
**Generated**: 2026-06-13T20:05:00Z
**Scenarios**: 30 total (5 smoke, 6 regression)
**Assumptions**: 5 total (3 high / 2 medium / 0 low confidence)
**Review required**: No

## Scope

The re-index pipeline (FEAT-MEM-07, part a) walks guardkit's authoritative
markdown corpus — seed modules, ADRs, review reports, and completed-task
outcomes — and turns each document into a typed payload (`seed_module`, `adr`,
`review_report`, `build_outcome`) via deterministic, front-matter/house-format
parsers with no language-model call. Each payload is published as a
`MemoryEpisodeV1` (content_format `json` + explicit `payload_type`) through the
live relay, which dispatches it to the FEAT-MEM-03 deterministic writer. Full-
corpus runs are idempotent and re-runnable: idempotency, versioned upsert, and
natural-key dedup are enforced downstream by the writer's content-hash upsert,
so a second run over an unchanged corpus is a no-op and an edited source updates
its record rather than duplicating it. Part (b) adds a backfill staging area
(`backfill/staging/`) for Fable-authored payloads that publish only after an
operator-controlled human review marker — gating frontier-authored content
behind review while reusing the same single write path (DECISION-DF-001: Fable
for offline authoring only, zero cloud on the publish path).

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 8 |
| Boundary conditions (@boundary) | 5 |
| Negative cases (@negative) | 10 |
| Edge cases (@edge-case) | 12 |

(Tags overlap: several scenarios carry both `@edge-case` and `@negative`, or
`@boundary` and `@negative`; the column counts every tag occurrence.
`@smoke`: 5, `@regression`: 6.)

## Deferred Items

None. All four proposal groups and the 6-scenario security/concurrency/
integration expansion were accepted.

## Open Assumptions (low confidence)

None. All 5 assumptions resolved at medium or high confidence and confirmed —
no `REVIEW REQUIRED` flag. Two medium-confidence items worth a glance during
planning:

- **ASSUM-003** — review-gate mechanism: an operator-controlled marker held
  *outside* the payload content. The concrete form (sidecar file, manifest
  entry, directory move) is a design decision for `/feature-plan`.
- **ASSUM-004** — unrecognized documents are skipped and recorded in the run
  report (accounted for, run not aborted), rather than parked/dead-lettered.

## Related acceptance criteria not specced here

Two FEAT-MEM-07 acceptance criteria sit adjacent to this pipeline and are
touched only lightly (one audit edge-case scenario each); they may warrant
their own scope in `/feature-plan`:

- Stream-vs-store audit script reporting 100% accounted (ingested or DLQ'd).
- Probe-set parity report generated against the re-indexed corpus.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Re-index Pipeline" \
      --context features/re-index-pipeline/re-index-pipeline_summary.md

Note: `@task:<TASK-ID>` tags are intentionally absent — `/feature-plan`
Step 11 links scenarios to the tasks it creates.
