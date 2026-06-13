# Fleet Memory — Phase CORE Build Plan

## Generated: 12 June 2026
## Companion: [phase-core-scope.md](phase-core-scope.md) — thesis, success criteria, what's in/out of scope
## Predecessor: Memory Relay scope at [`nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md`](../../../../nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md) (capture/buffer layer; D1–D11 inherited except where superseded below)
## Prerequisites: repo initialized from `nats-asyncio-service` (done 2026-06-12); capture hook wired (done); Fable 5 window open (~10 days from 2026-06-12); always-on nomic-embed at llama-swap :9000; NATS JetStream live.
## Status as of 2026-06-13: FEAT-MEM-01 **Landed** (FEAT-CA81, merged to `main` @ `2a8ae61`); FEAT-MEM-02 **Spec'd** (`/feature-spec` → `features/typed-payload-registry/`, uncommitted on `main`) — `/feature-plan` is next. NAS deploy (TASK-MEM-008) outstanding as an operator handoff.
## Plan-update convention (for context-switch resilience):
##   - **After `/feature-spec` lands:** flip the feature's row in "Feature Summary" to **Spec'd** with the GuardKit feature id; add a `**Status:**` line at the top of that feature's section noting the spec commit + features/<slug>/ path.
##   - **After `/feature-plan` lands:** flip the row to **Plan'd**; update the `**Status:**` line with plan commit + `.guardkit/features/FEAT-XXXX.yaml` + task-tree path.
##   - **After the feature lands:** flip the row to **Landed**; tick Acceptance Criteria; add impl + closure commits; strike through the Build Sequence entry.

---

## Context

Graphiti is being replaced as the fleet's development-knowledge memory. The full case is in the scope doc; the operational summary: TASK-REV-GROI found 0/10 consumption paths proven high-value; the write path costs ~28GB always-on (`qwen-graphiti`) after every consolidation route failed (findings §9.5–§9.8); the cloud fallback cost £30 in one weekend; and ADR-SP-007 (markdown authoritative) makes replacement a re-index rather than a migration. The Memory Relay (nats-infrastructure) provides durable LLM-free capture; this repo provides the store, the deterministic writer, retrieval, and the MCP surface.

**Division of labour across repos (cross-repo tasks created only on explicit instruction):**

| Repo | Owns | Phase CORE deliverable |
|---|---|---|
| nats-core | `MemoryEpisodeV1` envelope schema + publisher helper | Relay P1 (one small feature) |
| nats-infrastructure | MEMORY stream + consumer definitions, provisioning | Relay P2 (definitions only — drain worker does NOT live there; superseded, see RD-3) |
| **fleet-memory (this repo)** | Store, typed registry, deterministic writer, relay consumer, retrieval, MCP server, runbooks | FEAT-MEM-01..09 |
| guardkit | Publisher integration + read-path cutover | Coordinated rows inside FEAT-MEM-07/08 |

## What already exists

See scope doc table. Key for sequencing: the template gives Schemas/Handlers/Services layers with TestNatsBroker testing out of the box, so FEAT-MEM-04's consumer is a handler in an existing idiom, not new architecture; and nomic-embed is already always-on, so FEAT-MEM-01 has no serving-layer dependency beyond what's running today.

## What Phase CORE adds

Nine features. 01–03 are the spine (store, schemas, writer); 04–06 are the surfaces (relay, retrieval, MCP); 07–09 are population and cutover. 01→02→03 strictly sequential; 04 and 05 parallelizable after 03; 06 after 05; 07 after 03 (writer exists); 08 after 05+07; 09 last.

## Feature Summary

| Feature | Title | Status | GuardKit ID |
|---|---|---|---|
| FEAT-MEM-01 | Storage substrate (Postgres+pgvector, AsyncPostgresStore, embed fn) | **Landed** (NAS deploy pending op) | FEAT-CA81 |
| FEAT-MEM-02 | Typed payload registry | **Spec'd** | — (assigned at plan) |
| FEAT-MEM-03 | Deterministic writer | **Spec'd** | — (assigned at plan) |
| FEAT-MEM-04 | Relay integration (MEMORY consumer + chunk/embed path) | Not started | — |
| FEAT-MEM-05 | Retrieval API + context assembly | Not started | — |
| FEAT-MEM-06 | MCP server module | Not started | — |
| FEAT-MEM-07 | Re-index + Fable backfill | Not started | — |
| FEAT-MEM-08 | GuardKit read-path cutover | Not started | — |
| FEAT-MEM-09 | Cutover + decommission runbook | Not started | — |

## Architectural Constraints (carried from scope — enforce in every spec)

- DECISION-DF-001: Fable for authoring only; zero cloud in runtime paths.
- ADR-SP-007: store is an index; fixes go to source markdown + re-index.
- `MemoryEpisodeV1` frozen v1; engine mapping lives in this repo's services.
- Handler → Service unidirectional; TestNatsBroker; lifespan-managed pool; pydantic-settings.
- Underscores in all identifiers (`fleet_memory`, namespace tuples, Postgres objects).
- Two-layer idempotency: JetStream Msg-Id dedupe + natural-key upsert.

---

## FEAT-MEM-01: Storage Substrate

**Status:** Landed 2026-06-13 — `/feature-build FEAT-CA81` complete (all 13 tasks Coach-approved across 8 waves); merged to `main` via fast-forward @ `2a8ae61`; project scaffolding + coach config @ `0ca7feb`. Post-merge verification on `main`: **78 unit tests** (hermetic, NAS off) + **32 integration tests** (ephemeral Postgres 16 + pgvector, real nomic over Tailscale) green. 5/6 ACs met — NAS-deploy AC pending operator handoff **TASK-MEM-008** (deferred; `deploy/nas/deploy.sh` + `smoke.sh` ready, run from the Mac, then `/task-complete TASK-MEM-008`). One real bug fixed in-build: lifespan ignored `pg_connect_timeout_s` (psycopg-pool retried for its 30s default) — `async_store_context` now bounds context entry at `pg_connect_timeout_s + 5s` and raises a credential-free `TimeoutError`. The 3 low-confidence placeholders were verified and recorded by TASK-MEM-013 (`features/storage-substrate/storage-substrate_assumptions.yaml`, all `confidence: verified`). Prior: Plan'd 2026-06-12 (`/feature-plan`, review TASK-REV-CA81); all 34 scenarios `@task:`-tagged (R2), per-wave `pytest tests/unit` smoke gate (R3).

Postgres 16 + pgvector (durable instance on the Synology NAS per RD-4), `langgraph` `AsyncPostgresStore` with index config `{dims: 768, embed: <nomic via llama-swap :9000>}`, lifespan wiring, pydantic-settings (`FLEET_MEMORY_PG_DSN`, `FLEET_MEMORY_EMBED_URL`, `FLEET_MEMORY_EMBED_MODEL`), store smoke tests (put/get/search round-trip with real embeddings, marker-gated integration tests).

**Dev/test/prod topology (development is on the MacBook; state is on the NAS):**

| Instance | Where | Used by | Notes |
|---|---|---|---|
| Ephemeral test Postgres | MacBook, `docker run pgvector/pgvector:pg16` (compose file `deploy/local/`) | ALL automated test gates — unit, integration, AutoBuild quality gates | **Hermetic: AutoBuild must never depend on the NAS.** Parallel worktrees each get a throwaway instance (random port via env); no shared state, no network coupling, no test-data pollution |
| Durable shared Postgres | Synology NAS, Container Manager project (compose + notes in `deploy/nas/`) | Re-index target (07), MCP server, relay consumer, soak | Volume on a backed-up shared folder; port 5432 exposed to LAN/Tailscale only; reachable from the Mac during dev as `FLEET_MEMORY_PG_DSN` pointing at the NAS |

Embeddings always come from GB10 llama-swap `:9000` (Mac reaches it over Tailscale — the proven specialist-agent FEAT-RAG pattern); tests that don't need real vectors use a fake embed function so unit gates need no network at all.

**Pre-flight (verify before spec):** NAS CPU arch supports the `pgvector/pgvector:pg16` image (x86_64 Synology Plus models are fine); confirm the Container Manager deployment pattern matches how FalkorDB is run today so there's one NAS-container convention, not two.

### Spec & Plan Commands

```
# DONE 2026-06-12 → features/storage-substrate/ (34 scenarios, 13 assumptions):
# /feature-spec "Storage substrate: LangGraph AsyncPostgresStore on Postgres 16 + pgvector with nomic-embed-text-v1.5 768-dim embed function via llama-swap :9000; dual deploy targets — deploy/local ephemeral compose for hermetic Mac test gates (random-port, throwaway, used by ALL automated tests incl. AutoBuild) and deploy/nas Synology Container Manager compose for the durable shared instance (backed-up volume, LAN/Tailscale-only 5432); lifespan-managed pool; pydantic-settings DSN/embed config with .env.example profiles for mac-dev-vs-nas; fake-embed unit tests + marker-gated integration tests against the ephemeral instance + one documented smoke against the NAS instance"
/feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md
```

### Tasks (indicative — /feature-plan decides)

- `deploy/local/` ephemeral compose (random host port via env) + `deploy/nas/` Container Manager compose; `deploy.sh` + `smoke.sh` productized from [RUNBOOK-nas-postgres-deploy](../../runbooks/RUNBOOK-nas-postgres-deploy.md) Phases 2–3 (gates G2–G5 inline); pgvector extension migration
- Store factory + embed function (httpx client against OpenAI-compatible /v1/embeddings)
- Lifespan integration in app entry point; settings with `.env.example` covering mac-dev (NAS DSN over LAN/Tailscale) and test (ephemeral DSN) profiles
- Unit tests (fake embed, no network) + integration tests (ephemeral Postgres, real nomic over Tailscale, marker-gated) + NAS smoke script

### Acceptance Criteria

- [x] `store.aput` / `asearch` round-trip with real nomic embeddings against the ephemeral instance
- [x] Full test suite passes on the MacBook with the NAS powered off (hermeticity proven)
- [ ] NAS instance deployed via the runbook's scripted path (`deploy.sh`); `smoke.sh` (G2–G5) passes from the Mac; volume on a backed-up share; 5432 not exposed beyond LAN/Tailscale — **pending operator handoff TASK-MEM-008** (files ready in `deploy/nas/`)
- [x] Vector index created at 768 dims; search returns by similarity with metadata filter
- [x] No hyphens in any Postgres identifier; namespace tuples use underscores
- [x] Connection pool opens/closes cleanly under lifespan; settings via env only

## FEAT-MEM-02: Typed Payload Registry

**Status:** Spec'd 2026-06-13 via `/feature-spec` → `features/typed-payload-registry/` (29 scenarios; 11 assumptions — 4 low-confidence flagged REVIEW REQUIRED: domain_tags format, version-stamp semantics, source_ref optionality, self/cross-project supersession; `related_keys` deliberately deferred to retrieval/writer). Uncommitted on `main`. `/feature-plan` next.

Pydantic models in the Schemas layer: `AdrPayload`, `ReviewReportPayload`, `BuildOutcomePayload`, `PatternPayload`, `WarningPayload`, `SeedModulePayload`, `DocumentPayload` (generic). Conventions: `natural_key` property per type (e.g. `adr:guardkit:ADR_SP_007`), `supersedes: list[str]`, `domain_tags: list[str]`, `source_ref`, version stamp. Registry maps `payload_type` string → model class (the writer and the relay consumer both dispatch through it).

### Spec & Plan Commands

```
# /feature-spec done 2026-06-13 → features/typed-payload-registry/ (29 scenarios, 11 assumptions)
/feature-plan "Typed Payload Registry" --context features/typed-payload-registry/typed-payload-registry_summary.md
```

### Acceptance Criteria

- [ ] Every model rejects hyphenated keys/group identifiers at validation time
- [ ] Natural keys are stable across re-serialization (property-based test)
- [ ] Registry round-trips `payload_type` → model → JSON → model
- [ ] `supersedes` accepts only natural-key-shaped references

## FEAT-MEM-03: Deterministic Writer

**Status:** Spec'd 2026-06-13 via `/feature-spec` → `features/deterministic-writer/` (29 scenarios; 10 assumptions — 2 low-confidence flagged REVIEW REQUIRED: forward supersession of a not-yet-written key (ASSUM-008), batch-write / partial-batch failure mode (ASSUM-010)). Zero-LLM guarantee captured as an enforceable negative scenario; idempotency, supersession, and re-index-idempotency suites covered. Uncommitted on `main`. `/feature-plan` next.

Service: typed payload → store record(s). UUIDv5 from natural key; idempotent upsert (same key + same content hash = no-op; same key + new content = versioned update); supersession handling (mark superseded record, link successor — a dict update, no LLM); embed-on-write via the store's index config; per-project namespace tuples `("fleet_memory", project, payload_type)`.

### Spec & Plan Commands

```
# /feature-spec done 2026-06-13 → features/deterministic-writer/ (29 scenarios, 10 assumptions)
/feature-plan "Deterministic Writer" --context features/deterministic-writer/deterministic-writer_summary.md
```

### Acceptance Criteria

- [ ] Writing the same payload twice produces one record (audited via store list)
- [ ] Superseding ADR marks predecessor `superseded_by` and excludes it from default retrieval
- [ ] No code path in the writer can construct an LLM client (negative import test)
- [ ] Write throughput: full guardkit seed corpus in < 5 minutes (measured in 07)

## FEAT-MEM-04: Relay Integration

FastStream handler on the MEMORY stream durable consumer: `content_format: json` + `payload_type` → registry → writer; `markdown`/`text` → chunking service (heading-aware, ~1K-token chunks, overlap) → embed → store under `("fleet_memory", project, "chunk")` with source_ref metadata. Ack/nak/DLQ semantics per relay scope D5/D9; ingestion ledger via natural keys (relay O3 resolved: the writer's idempotency IS the ledger for structured; chunk path uses episode_id keys). The drain worker concept collapses into this consumer — no residency gating needed, because nothing here needs a big model.

### Spec & Plan Commands

```
/feature-spec "Relay integration: FastStream durable consumer on MEMORY stream consuming MemoryEpisodeV1 from nats-core; structured_json episodes dispatch through payload registry to deterministic writer; markdown/text episodes chunk+embed with heading-aware chunking; ack/nak/DLQ per relay scope; TestNatsBroker test suite incl. poison message and redelivery idempotency"
/feature-plan FEAT-XXXX
```

### Acceptance Criteria

- [ ] Publish 3 structured + 2 markdown episodes via TestNatsBroker → 3 typed records + N chunks
- [ ] Redelivery of an acked episode changes nothing (two-layer idempotency proven)
- [ ] Malformed body → DLQ subject after max_deliver, consumer continues
- [ ] No `qwen-graphiti` or any chat-completion traffic during ingestion (serving-layer check)

## FEAT-MEM-05: Retrieval API + Context Assembly

Service: `search(project, payload_types, domain_tags, query, token_budget, include_superseded=False)` → ranked, token-budgeted context block. Port the semantics of guardkit's job-specific context assembly (overview/patterns/warnings composition by complexity band). Coverage-score hook (how much of the budget was filled, from which types) for observability and the probe-set evaluation.

### Spec & Plan Commands

```
/feature-spec "Retrieval API: search with project/payload-type/domain-tag filters + vector query + token budget, default supersession exclusion, ranked composition porting guardkit job-specific context semantics, coverage scoring; probe-set evaluation harness for the 15-query retrieval-parity gate"
/feature-plan FEAT-XXXX
```

### Acceptance Criteria

- [ ] Budgeted assembly never exceeds token budget (tiktoken-measured)
- [ ] Superseded records excluded by default, includable by flag
- [ ] Probe-set harness runs the ≥15 fixed queries and emits a parity report vs recorded Graphiti answers
- [ ] p95 search latency < 200ms against the re-indexed corpus (local network)

## FEAT-MEM-06: MCP Server Module

`mcp/` module (FastMCP, patterns from `fastmcp-python` template as reference): tools `memory_search`, `memory_write_payload`, `memory_supersede`; resources for project listing. Claude Desktop `.mcp.json` entry replacing the Graphiti MCP. Write tools dispatch through the same registry+writer (no second write path).

### Spec & Plan Commands

```
/feature-spec "FastMCP server module: memory_search / memory_write_payload / memory_supersede tools over the retrieval API and deterministic writer, project resources, stdio transport for Claude Desktop, replacing the Graphiti MCP; tool-contract tests"
/feature-plan FEAT-XXXX
```

### Acceptance Criteria

- [ ] Claude Desktop session can search and write a typed ADR end-to-end
- [ ] MCP writes are byte-identical in store form to relay writes of the same payload
- [ ] Graceful degradation message when Postgres unreachable (no crash)

## FEAT-MEM-07: Re-index + Fable Backfill

Two parts. (a) Re-index script: walk guardkit's authoritative markdown (seed modules, ADRs, review reports, completed-task outcomes), parse to typed payloads (deterministic parsers — front-matter and house formats are regular), publish via nats-core helper (exercising the full relay path). (b) Fable backfill: one-time, window-bound job where Fable 5 reads the genuinely unstructured legacy docs and authors typed payloads for human review before publishing — output is reviewed markdown/JSON in the repo, so the result is re-runnable forever without any frontier model.

### Spec & Plan Commands

```
/feature-spec "Re-index pipeline: deterministic markdown-to-typed-payload parsers for guardkit seed modules, ADRs, review reports and task outcomes, publishing via nats-core MemoryEpisodeV1 through the live relay; idempotent full-corpus runs; backfill staging area for Fable-authored payloads with human review gate before publish"
/feature-plan FEAT-XXXX
```

### Acceptance Criteria

- [ ] Full guardkit re-index < 5 min, zero LLM calls, idempotent on second run
- [ ] Backfill payloads land in `backfill/staging/` and publish only after review flag
- [ ] Stream-vs-store audit script reports 100% accounted (ingested or DLQ'd)
- [ ] Probe-set parity report generated against this corpus (feeds criterion 1)

## FEAT-MEM-08: GuardKit Read-Path Cutover (cross-repo)

GuardKit's coach context builder, feature-plan context, and CLI retrieval point at fleet-memory's retrieval API (thin client or MCP). The GROI anti-criterion: reads must demonstrably fire in real pipeline runs. Coordinated guardkit tasks created on explicit instruction when 05+07 land.

### Acceptance Criteria

- [ ] One real `/feature-plan` and one AutoBuild run show fleet-memory retrieval in history files
- [ ] Graphiti client paths in guardkit behind a feature flag, default off

## FEAT-MEM-09: Cutover + Decommission Runbook

`docs/runbooks/RUNBOOK-graphiti-cutover.md` in house style (phased bash, PASS/FAIL gates, decision-gate table, rollback commands, explicit what-NOT-to-do): qwen-graphiti out of always-on preload; Gemini fallback blocks deleted from all `graphiti.yaml`s; Graphiti/FalkorDB frozen read-only for the soak; steady-state memory measured; findings doc §9.x entry in guardkit; archive decision after soak.

### Acceptance Criteria

- [ ] ~28GB steady-state reduction measured and recorded
- [ ] £0 cloud on memory path (config grep proves no Gemini fallback remains)
- [ ] Rollback path tested on paper: unfreeze Graphiti + flag flip restores old reads

---

## Build Sequence (Fable window: ~2026-06-12 → ~2026-06-21; half-days assumed around Evri)

| Day | Focus |
|---|---|
| 1 (Fri 12) | This pair; ~~`/feature-spec` + `/feature-plan` FEAT-MEM-01~~ ✅; relay P1 spec in nats-core (on instruction) |
| 2–3 (wknd) | ~~FEAT-MEM-01 build~~ ✅ (landed 06-13 @ `2a8ae61`; NAS deploy pending op) + FEAT-MEM-02 build; ~~Postgres live on NAS~~ (pending TASK-MEM-008); relay P2 stream definitions land |
| 4 (Mon 15) | FEAT-MEM-03 writer |
| 5 (Tue 16) | FEAT-MEM-04 relay consumer; first end-to-end publish→store |
| 6 (Wed 17) | FEAT-MEM-05 retrieval + probe harness; record Graphiti baseline answers before any freeze |
| 7 (Thu 18) | FEAT-MEM-06 MCP; FEAT-MEM-07 re-index parsers |
| 8 (Fri 19) | FEAT-MEM-07 full re-index + **Fable backfill day** (the window-critical task) |
| 9 (Sat 20) | FEAT-MEM-08 guardkit cutover; parity report; audit |
| 10 (Sun 21) | FEAT-MEM-09 cutover runbook executed; preload change; slack + findings |

**Cut lines if the window compresses:** FEAT-MEM-06 (MCP) and FEAT-MEM-08 can slip past the window — they don't need Fable. FEAT-MEM-07's backfill is the only deliverable that genuinely expires with the subscription; protect Day 8.

## Resolved Decisions

| # | Decision | Notes |
|---|---|---|
| RD-1 | Substrate = LangGraph `AsyncPostgresStore` (Postgres+pgvector) | Own the writer and retrieval, not the storage engine; native to the DeepAgents stack every agent is migrating to |
| RD-2 | Home = fleet-memory repo, `nats-asyncio-service` template | Fleet service, not NATS infra, not guardkit |
| RD-3 | **Supersedes relay D4:** relay consumer (drain worker) lives in fleet-memory | The writer it calls lives here; residency gating dropped — nothing on this write path needs a big model. nats-infrastructure keeps stream/consumer *definitions* only |
| RD-4 | Postgres container on Synology NAS alongside FalkorDB | State lives with the NAS backup regime; GB10 stays compute |
| RD-5 | Hard cut after Day-9 audit; Graphiti frozen read-only through soak as comparison baseline only | GROI showed the reads Graphiti would backstop were barely connected; dual-run is ceremony |
| RD-6 | Supersession is declared, never inferred | Field on the payload; replaces LLM temporal invalidation |
| RD-7 | No LLM extraction in Phase CORE; unstructured = chunk+embed | Raw episodes persist in MEMORY stream; enrichment stays a future batch option |
| RD-8 | Trace proxy demoted to optional; 7BFP/VLLW on hold; Hindsight evaluation closed; upstream PRs goodwill-only | All were instruments of a decision now made |

## Open Decisions

| # | Question | Recommendation | Resolve by |
|---|---|---|---|
| OD-1 | Chunking parameters for markdown path (size/overlap/heading awareness) | Start 1K tokens, 15% overlap, heading-aware; tune only on probe-set evidence | FEAT-MEM-04 spec |
| OD-2 | Probe-set composition (which 15+ queries, from whose history) | Draw from coach-context + feature-plan invocations in guardkit history files; freeze before FEAT-MEM-05 build | Day 6 |
| OD-3 | guardkit client mechanism for 08 (thin HTTP/lib client vs MCP) | Thin library client (import via git+ssh like nats-core); MCP stays a Desktop surface | FEAT-MEM-08 |
| OD-4 | Graphiti archive timing post-soak | 2-week soak then archive FalkorDB volume to NAS cold storage | FEAT-MEM-09 runbook |
| OD-5 | Runtime host for the relay consumer + MCP-adjacent services in production | GB10 container (compute box: beside NATS and llama-swap, localhost embeddings, LAN to NAS Postgres) — NAS stays storage-only, Mac stays a dev surface that can sleep | FEAT-MEM-04 spec |

## Risks

| Risk | Mitigation |
|---|---|
| Retrieval parity fails on relationship-style queries (the one thing graph traversal did) | Probe set includes the worst cases deliberately; `related_keys` field on payloads gives cheap one-hop links without a graph engine; if still short, that's the recorded trigger for revisiting extraction — not a silent fudge |
| Fable window closes before Day 8 backfill | Backfill is staged + reviewable; worst case the unstructured legacy slice ships chunk-only (already the v1 contract) and typed backfill happens later with a local model |
| Evri load compresses implementation days | Pipeline does the building; cut lines defined (06, 08 can slip); spine (01–05, 07) protected |
| NAS Postgres performance under embed-heavy re-index | Embeddings computed GB10-side via llama-swap; Postgres only stores; if insert throughput disappoints, batch upserts (writer already batches) |
| Two write surfaces drift (MCP vs relay) | Both dispatch through the single registry+writer (FEAT-MEM-06 AC enforces byte-identical store form) |

---

*Build plan authored 12 June 2026. Maintained per the plan-update convention above; history of every spec/plan/build invocation auto-captured to `docs/history/` by the capture hook.*
