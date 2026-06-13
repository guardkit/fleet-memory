# Feature Spec Summary: Relay Integration (FEAT-MEM-04)

**Stack**: python
**Generated**: 2026-06-13T11:04:22Z
**Scenarios**: 32 total (5 smoke, 7 regression)
**Assumptions**: 11 total (2 high / 6 medium / 3 low confidence)
**Review required**: Yes

## Scope

The relay consumer is a FastStream durable consumer on the MEMORY stream that
ingests `MemoryEpisodeV1` envelopes published from nats-core. It routes by
`content_format`: structured `json` episodes dispatch through the typed payload
registry (FEAT-MEM-02) to the deterministic writer (FEAT-MEM-03) as typed
records; `markdown` and `text` episodes are split into heading-aware chunks,
embedded, and stored under `(fleet_memory, project, chunk)` with their source
reference. Episodes are acknowledged only after a durable commit; transient
downstream failures are redelivered while poison episodes are parked on the
dead-letter subject after `max_deliver`. Two-layer idempotency — the writer's
natural-key upsert for structured payloads and `episode_id`-derived keys for
chunks — makes at-least-once redelivery inert. No language model is on the
write path.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 7 |
| Boundary conditions (@boundary) | 6 |
| Negative cases (@negative) | 12 |
| Edge cases (@edge-case) | 13 |
| Smoke (@smoke) | 5 |
| Regression (@regression) | 7 |

(A scenario may carry more than one category tag, so counts overlap; the 32
distinct scenarios are grouped as Key 7 / Boundary 6 / Negative 6 / Edge 7 /
Edge-case expansion 6.)

## Deferred Items

None — all four base groups and all three edge-case expansion groups were
accepted during curation.

## Open Assumptions (low confidence)

These need human verification before the spec drives implementation. All three
trace to the relay ack/nak/DLQ contract (D5/D9), which lives in the sibling
`nats-infrastructure` repo and was not readable from this repository:

- **ASSUM-005** — `max_deliver` is 5 before an episode is parked.
- **ASSUM-006** — failed episodes go to a dedicated dead-letter (DLQ) subject (exact name in relay scope D9).
- **ASSUM-013 / empty-body** (ASSUM not numbered as low elsewhere): an empty-body prose episode produces zero chunks and is acknowledged rather than parked — see the `# [ASSUMPTION: confidence=low]` annotation in the feature file.

> Verify ASSUM-005 and ASSUM-006 against the nats-infrastructure memory-relay
> scope (D5/D9) before build, and confirm the empty-body and partial-chunk
> handling (low-confidence annotations in the feature file) reflect the intended
> design.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Relay Integration" \
      --context features/relay-integration/relay-integration_summary.md
