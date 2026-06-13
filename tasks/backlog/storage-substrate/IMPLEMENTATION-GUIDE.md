# Implementation Guide: Memory Storage Substrate (FEAT-CA81 / FEAT-MEM-01)

**Parent review**: TASK-REV-CA81 ([report](../../../.claude/reviews/TASK-REV-CA81-review-report.md))
**BDD spec**: features/storage-substrate/storage-substrate.feature (34 scenarios)
**Trade-off priority** (Context A): hermetic correctness — the full suite passes with the NAS powered off; AutoBuild never touches the NAS.
**Approach** (Context B confirmed): deploy/local compose + UUID-project pytest fixtures · plain httpx embed callable with injectable fake · minimal FastStream shell with lifespan-wired `AsyncPostgresStore` · single `FLEET_MEMORY_` settings class · pgvector via `initdb/01_extensions.sql`.

## Data Flow: Read/Write Paths

```mermaid
flowchart LR
    subgraph Writes["Write Paths"]
        W1["store.aput()\nvia async_store_context\n(TASK-MEM-005)"]
        W2["embed callable → llama-swap :9000\n/v1/embeddings (TASK-MEM-003)"]
        W3["deploy.sh → NAS schema/init\n(TASK-MEM-007/008)"]
    end

    subgraph Storage["Storage"]
        S1[("ephemeral Postgres\npgvector :random_port\n(throwaway, per-run)")]
        S2[("NAS Postgres\npgvector :5432\n(durable, backed-up)")]
    end

    subgraph Reads["Read Paths"]
        R1["aget / asearch\nintegration tests\n(TASK-MEM-010/011/012)"]
        R2["smoke.sh G4\npsql SELECT 1 (operator)"]
        R3["production retrieval\n(FEAT-MEM-05)"]
    end

    W2 -->|"768-dim vectors"| W1
    W1 -->|"test profile DSN"| S1
    W3 -->|"operator-only"| S2

    S1 -->|"same store context"| R1
    S2 -->|"LAN/Tailscale"| R2
    S2 -.->|"NOT WIRED (deferred)"| R3

    style R3 fill:#fcc,stroke:#c00
    style S1 fill:#cfc,stroke:#090
```

_Look for: every automated write/read stays on the ephemeral instance (green); the NAS is written only by the operator path and read only by the operator smoke gate._

**Disconnection Alert**: 1 read path has no caller in this feature. The NAS durable
instance has no production reader/writer inside FEAT-MEM-01 — by design. Production
writes arrive with FEAT-MEM-03/04 (writer + relay consumer) and production reads
with FEAT-MEM-05 (retrieval API); the `mac-dev` profile in `.env.example`
(TASK-MEM-002) is the bridge that will point the service at the NAS. **Deferral
acknowledged at the [I]mplement checkpoint — tracked here, no wiring task added.**

## Integration Contracts (sequence)

```mermaid
sequenceDiagram
    participant App as FastStream lifespan (006)
    participant Set as Settings (002)
    participant Store as async_store_context (005)
    participant Embed as embed callable (003)
    participant LS as llama-swap :9000
    participant PG as ephemeral Postgres (004)

    App->>Set: Settings() from FLEET_MEMORY_ env
    Set-->>App: pg_dsn, embed_url, pool + timeout bounds
    App->>Store: async with async_store_context(settings)
    Store->>PG: connect (pool min/max, connect_timeout_s)
    Store->>PG: store.setup() (idempotent)
    Store-->>App: ready AsyncPostgresStore

    Note over App,PG: write path
    App->>Store: aput(namespace, key, value)
    Store->>Embed: embed([content]) — bounded by embed_timeout_s
    Embed->>LS: POST /v1/embeddings
    LS-->>Embed: 768-dim vectors (else EmbedDimensionError)
    Store->>PG: upsert row + vector

    Note over App,PG: read path
    App->>Store: asearch(query, filter)
    Store->>Embed: embed([query])
    Store->>PG: vector similarity + metadata filter
    PG-->>App: ranked results with scores

    Note over Store,PG: on embed failure: no partial write reaches PG (ASSUM-005)
```

_Look for: embeddings are fetched and passed onward into the same `aput` call — no fetch-then-discard point exists; an embed failure aborts the write before Postgres sees it._

## Task Dependencies

```mermaid
graph TD
    T1[TASK-MEM-001 Scaffold] --> T2[TASK-MEM-002 Settings]
    T1 --> T4[TASK-MEM-004 Ephemeral compose+fixtures]
    T2 --> T3[TASK-MEM-003 Embed callable]
    T4 --> T7[TASK-MEM-007 NAS deploy files]
    T2 --> T5[TASK-MEM-005 Store factory]
    T3 --> T5
    T3 --> T6[TASK-MEM-006 App shell lifespan]
    T5 --> T6
    T3 --> T9[TASK-MEM-009 Unit suite]
    T5 --> T9
    T6 --> T9
    T4 --> T10[TASK-MEM-010 Integration: semantics+pool]
    T5 --> T10
    T6 --> T10
    T10 --> T11[TASK-MEM-011 Integration: boundaries]
    T10 --> T12[TASK-MEM-012 Integration: metadata+concurrency]
    T7 --> T8[TASK-MEM-008 NAS deploy ⚠ operator]
    T9 --> T13[TASK-MEM-013 Assumption record]
    T10 --> T13
    T11 --> T13
    T12 --> T13

    style T2 fill:#cfc,stroke:#090
    style T4 fill:#cfc,stroke:#090
    style T3 fill:#cfc,stroke:#090
    style T7 fill:#cfc,stroke:#090
    style T9 fill:#cfc,stroke:#090
    style T10 fill:#cfc,stroke:#090
    style T11 fill:#cfc,stroke:#090
    style T12 fill:#cfc,stroke:#090
    style T8 fill:#ffe9a8,stroke:#b8860b
```

_Tasks with green background run in parallel within their wave; amber = operator_handoff (AutoBuild skips it)._

## §4: Integration Contracts

### Contract: FLEET_MEMORY_PG_DSN
- **Producer task:** TASK-MEM-002 (Settings class)
- **Consumer task(s):** TASK-MEM-005 (store factory), TASK-MEM-006 (lifespan)
- **Artifact type:** environment variable / Settings field
- **Format constraint:** Plain `postgresql://user:pass@host:port/dbname` conninfo — psycopg3 format required by langgraph `AsyncPostgresStore` (langgraph-checkpoint-postgres uses psycopg3 + psycopg-pool). **NO `+asyncpg` dialect suffix.**
- **Validation method:** Coach runs TASK-MEM-005's seam test `test_pg_dsn_format_is_psycopg3_conninfo`; `.env.example` shows the plain format

### Contract: EMBED_CALLABLE
- **Producer task:** TASK-MEM-003 (embed callable)
- **Consumer task(s):** TASK-MEM-005 (store index config)
- **Artifact type:** Python async callable
- **Format constraint:** `async (list[str]) -> list[list[float]]`, exactly `settings.embed_dims` (768) floats per vector; raises `EmbedDimensionError` / `EmbedTimeoutError` / `EmbedServiceError` — never returns malformed vectors
- **Validation method:** Coach runs TASK-MEM-005's seam test `test_embed_callable_returns_768_dim_vectors`; dimension-mismatch unit rows in TASK-MEM-003

### Contract: STORE_CONTEXT
- **Producer task:** TASK-MEM-005 (store factory)
- **Consumer task(s):** TASK-MEM-006 (lifespan), TASK-MEM-010 (integration tier)
- **Artifact type:** asynccontextmanager
- **Format constraint:** `async_store_context(settings, embed_fn=None)` yields a ready `AsyncPostgresStore` (setup() already run, idempotent); exit releases every connection
- **Validation method:** TASK-MEM-006 seam shape-test; TASK-MEM-010 pool-lifecycle test (pg_stat_activity before/after)

### Contract: EPHEMERAL_PG_DSN
- **Producer task:** TASK-MEM-004 (ephemeral compose + fixtures)
- **Consumer task(s):** TASK-MEM-010 (seam owner); TASK-MEM-011/012 inherit via the shared conftest fixture
- **Artifact type:** pytest session fixture yielding a DSN string
- **Format constraint:** plain `postgresql://` at `127.0.0.1` on a random non-5432 port; data throwaway per session; never references the NAS host
- **Validation method:** Coach runs TASK-MEM-010's seam test `test_ephemeral_dsn_is_local_random_port`; TASK-MEM-012's hermeticity grep

## Execution Strategy

| Wave | Tasks | Parallel? |
|---|---|---|
| 1 | TASK-MEM-001 scaffold | — |
| 2 | TASK-MEM-002 settings ∥ TASK-MEM-004 ephemeral compose | ⚡ 2-way (disjoint trees: `src/` vs `deploy/local/`+`tests/conftest`) |
| 3 | TASK-MEM-003 embed ∥ TASK-MEM-007 NAS files | ⚡ 2-way (`src/fleet_memory/embed.py` vs `deploy/nas/`) |
| 4 | TASK-MEM-005 store factory · TASK-MEM-008 NAS deploy (operator, skipped by AutoBuild) | mixed |
| 5 | TASK-MEM-006 app shell | — |
| 6 | TASK-MEM-009 unit suite ∥ TASK-MEM-010 integration semantics | ⚡ 2-way (`tests/unit/` vs `tests/integration/`) |
| 7 | TASK-MEM-011 boundaries ∥ TASK-MEM-012 metadata+concurrency | ⚡ 2-way (disjoint test files) |
| 8 | TASK-MEM-013 assumption record | — |

Execution preference (Context B): **auto-detect** — /feature-build runs the 2-way waves concurrently where the environment allows, sequential otherwise. Estimated ~10.5 h AutoBuild total, ~6.5–7 h critical path. Integration waves (6–7) need Docker + Tailscale route to GB10; unit gates need neither.

## Assumption Verification Map (Context A: defaults + verify)

| Assumption | Placeholder | Encoded as | Measured by | Recorded by |
|---|---|---|---|---|
| ASSUM-004 pool overflow queues | pool=10 | `pg_pool_max=10` | TASK-MEM-010 (15 concurrent aputs) | TASK-MEM-013 |
| ASSUM-006 startup fail-fast | ≤10 s | `pg_connect_timeout_s=10.0` | TASK-MEM-006 + 010 (closed port) | TASK-MEM-013 |
| ASSUM-008 embed bound | 10 s | `embed_timeout_s=10.0` | TASK-MEM-003 (MockTransport hang) | TASK-MEM-013 |
| ASSUM-002 default search limit | ≤10 | store default | TASK-MEM-011 | TASK-MEM-013 |

## Risks (from review — full detail in the report)

- **R1** psycopg-pool may raise on overflow rather than queue → TASK-MEM-010 AC6 detects; record-and-revise, not blocking
- **R2** integration tier needs Tailscale to GB10 → marker exclusion keeps the default run hermetic; documented in pytest config
- **R3** initdb scripts don't re-run on existing volumes → fixture uses `down -v` + fresh anonymous volumes; pgvector presence asserted after startup
- **R4** health-check race before init SQL completes → fixture waits on `pg_isready` healthcheck, not the port
- **R5** `langgraph-checkpoint-postgres` index-config shape unverified → TASK-MEM-001 import AC + TASK-MEM-005 verification AC surface it in Wave 1/4
- **R6** stray operator `.env` could hijack the test tier → env-var-over-dotenv precedence asserted in TASK-MEM-002

## Operator Follow-up

One task is `operator_handoff`: **TASK-MEM-008** (NAS deploy execution + smoke
G2–G5 + reboot persistence G6). AutoBuild skips it; `/feature-complete` surfaces
its checklist after merge. Prerequisite one-time Phase 0 (SSH key, sudoers,
firewall) is in the runbook.
