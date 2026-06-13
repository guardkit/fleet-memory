# Feature: Deterministic Writer (FEAT-MEM-03)

Turns a typed payload from the registry (FEAT-MEM-02) into `AsyncPostgresStore`
records with **zero language-model calls**: stable UUIDv5 identity from the
natural key, content-hash upsert (same key + same content = no-op; same key +
new content = versioned update), declared supersession (mark predecessor
`superseded_by`, exclude from default retrieval), embed-on-write, and per-project
namespaces `("fleet_memory", project, payload_type)`.

- **Spec**: [deterministic-writer.feature](../../../features/deterministic-writer/deterministic-writer.feature) (29 scenarios; 10 confirmed assumptions)
- **Guide**: [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md) (data-flow + integration-contract + dependency diagrams, §4 contracts)
- **Feature file**: `.guardkit/features/FEAT-MEM-03.yaml`

## Prerequisite

FEAT-MEM-02 (typed payload registry) must be merged to `main` before running
`/feature-build FEAT-MEM-03` — the writer imports `fleet_memory.payloads`.

## Tasks

| ID | Title | Type | Wave | Deps |
|----|-------|------|------|------|
| TASK-DW-001 | Record identity and content-hash helpers | feature | 1 | — |
| TASK-DW-002 | Deterministic writer core - idempotent content-hash upsert | feature | 2 | DW-001 |
| TASK-DW-003 | Declared supersession linking | feature | 3 | DW-002 |
| TASK-DW-004 | Idempotency and zero-LLM test suite | testing | 3 | DW-002 |
| TASK-DW-005 | Supersession test suite | testing | 4 | DW-003 |

## Execution

```bash
# After FEAT-MEM-02 is merged:
/feature-build FEAT-MEM-03
```

Waves: `[DW-001] → [DW-002] → [DW-003 ‖ DW-004] → [DW-005]`. Smoke gate
(`pytest tests/unit -x`) runs after Wave 3.
