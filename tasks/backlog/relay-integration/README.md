# Relay Integration (FEAT-MEM-04)

Durable FastStream consumer on the MEMORY stream that ingests `MemoryEpisodeV1`
envelopes, routes by `content_format`, and stores them losslessly with
at-least-once-safe idempotency. No language model on the write path.

- **Review:** TASK-REV-RLY04
- **Spec:** `features/relay-integration/relay-integration.feature` (32 scenarios)
- **Feature file:** `.guardkit/features/FEAT-MEM-04.yaml`
- **Guide:** [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md)

## Tasks

| Task | Title | Type | Cx | Wave |
|------|-------|------|----|----|
| TASK-RLY-001 | MemoryEpisodeV1 schema, ContentFormat enum, Chunk model | declarative | 3 | 1 |
| TASK-RLY-002 | Exception taxonomy (Poison vs Transient) | declarative | 3 | 1 |
| TASK-RLY-003 | Heading-aware prose chunker | feature | 6 | 2 |
| TASK-RLY-004 | Chunk writer (episode_id-derived ids, embed-on-write) | feature | 6 | 2 |
| TASK-RLY-005 | RelayService.ingest routing + two-layer idempotency | feature | 7 | 3 |
| TASK-RLY-006 | Thin MEMORY-stream handler: ack/nak/DLQ + settings | feature | 6 | 4 |
| TASK-RLY-007 | Verify D5/D9 (max_deliver, DLQ subject, empty-body) | operator_handoff | 2 | — |

## Reuses (already built)

- `DeterministicWriter` — `src/fleet_memory/writer/core.py` (FEAT-MEM-03)
- `PAYLOAD_REGISTRY` / `get_model_for_type` — `src/fleet_memory/payloads/registry.py` (FEAT-MEM-02)
- `async_store_context`, `validate_namespace` — `src/fleet_memory/store.py`
- embed-on-write via store index config — `src/fleet_memory/embed.py`

## Operator follow-up

1 task (`TASK-RLY-007`) — verify the ack/nak/DLQ contract against the sibling
`nats-infrastructure` repo before production. Run `/feature-complete` post-merge
for the full checklist.

## Next steps

```bash
# Verify the feature file, then build
guardkit feature validate FEAT-MEM-04
/feature-build FEAT-MEM-04
```
