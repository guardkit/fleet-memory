# Phase CORE Scope — Fleet Memory: Typed Deterministic Store Replacing Graphiti

## For: Claude Code `/system-arch` → `/system-design` → `/feature-spec` → `/feature-plan` → AutoBuild
## Generated: 12 June 2026
## Status: **Phase CORE not started.** Repo initialized from `nats-asyncio-service` template 2026-06-12; slash-command capture hook wired same day. Fable 5 subscription window: ~10 days from 2026-06-12 — the one-time backfill (FEAT-MEM-07) and heavy planning sessions must land inside it.
## Predecessor: Graphiti/FalkorDB memory estate (guardkit + fleet), and the Memory Relay scope at [`nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md`](../../../../nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md) — capture/buffer decisions D1–D11 there are inherited unless explicitly superseded below.
## Companion: [phase-core-build-plan.md](phase-core-build-plan.md) — feature-by-feature task breakdown, day-by-day plan, prefilled spec commands, risks.

---

## Thesis

Phase CORE exists to test one claim:

> A typed, deterministic memory store (Postgres + pgvector behind LangGraph `AsyncPostgresStore`), fed by the NATS episode relay and embedding with the always-on nomic endpoint, can replace Graphiti as the fleet's development-knowledge memory — with **zero LLM on the write path** for structured content, retrieval quality **≥ Graphiti** on real job-context queries, the **~28GB always-on extraction model retired**, and the **cloud fallback deleted** — built, re-indexed, and cut over inside the 10-day Fable 5 window.

If true, `qwen-graphiti` leaves the preload permanently, the Gemini fallback path dies, the guardkit/graphiti fork stops mattering, and every fleet agent (including AWS-deployed ones) gets memory capture as a fire-and-forget NATS publish. If false at the retrieval-quality gate, the diagnosis (filter miss, embedding miss, missing relationship traversal) is recorded against the GROI framework and Graphiti unfreezes — the relay, schemas, and deterministic writer survive that outcome unchanged.

## Why now

Four things converged this week:

| Driver | Evidence |
|---|---|
| Graphiti's value is unproven where it matters | TASK-REV-GROI: 10 consumption paths, **0 high-value**, 4 potential, 4 low-value, 1 dead; recommended strategy "connect, measure, decide" |
| The carrying cost is daily and structural | ~28GB always-on `qwen-graphiti` pin; consolidation routes all failed (AUTOBUILD-ON-LLAMA-SWAP-findings §9.5–§9.8); £30 Gemini weekend; fork maintenance (guardkit/graphiti fixes #5, #8–#12) |
| Migration is free by design | ADR-SP-007: markdown is authoritative, Graphiti was only an index. Replacement = re-index from source, not data rescue |
| Fable 5 window | ~10 days of frontier capacity for planning sessions and the one-time unstructured-legacy backfill ("teacher funds its own replacement", executed literally) |

The workload decomposition that makes the thesis credible: the majority of fleet memory writes are **structured at source** (ADRs, review reports, build outcomes, decision logs, seed modules — typed, keyed, versioned). Running those through LLM extraction was solving a problem we don't have. The genuinely unstructured slice (third-party docs, conversation capture) ships as chunk+embed with **no extraction at all** in this phase — raw episodes remain durably in the MEMORY stream, so LLM enrichment stays a future batch option, never a gate.

## What already exists

| Capability | Where | State |
|---|---|---|
| Repo skeleton: FastStream + Pydantic layered service (Entry/App/Config/Schemas/Handlers/Services), TestNatsBroker testing, lifespan management | this repo, from `nats-asyncio-service` template | ✅ initialized 2026-06-12 |
| Slash-command capture hook → `docs/history/` (fine-tune corpus) | `.claude/hooks/capture_slash_command.py` | ✅ wired 2026-06-12, verbatim from specialist-agent |
| Memory Relay scope (capture envelope `MemoryEpisodeV1`, MEMORY stream, drain gating, idempotency, DLQ) | nats-infrastructure spec | ✅ scoped 2026-06-12; relay D1–D11 inherited |
| NATS JetStream server, accounts (APPMILLA/FINPROXY), declarative stream provisioning | nats-infrastructure | ✅ live |
| nats-core schema/client package pattern (`pip install git+ssh`) | nats-core | ✅ live; memory schemas are a cross-repo deliverable |
| Always-on nomic-embed-text-v1.5 (768-dim) via llama-swap :9000 | GB10 | ✅ live |
| Authoritative markdown corpus: guardkit 22 seed modules, ADRs, review reports, task outcomes | guardkit et al. | ✅ on disk — the re-index source |
| GuardKit retrieval surfaces to reconnect (coach context, feature-plan context, job-specific assembly) | guardkit | ⚠️ exist but per GROI barely connected — FEAT-MEM-08 is the fix |

## What Phase CORE adds — at scope level

Detailed tasks live in [phase-core-build-plan.md](phase-core-build-plan.md). Scope-level shape:

| # | Component | Why |
|---|---|---|
| FEAT-MEM-01 | Storage substrate — Postgres 16 + pgvector container, `AsyncPostgresStore` wiring, nomic embed function, lifespan + settings | The foundation every other feature writes to and reads from. Proves the store primitive with the local embedding endpoint before anything is built on it. |
| FEAT-MEM-02 | Typed payload registry — Pydantic models for ADR, ReviewReport, BuildOutcome, Pattern, Warning, SeedModule, Document; natural-key + supersession conventions | The schema layer that makes writes deterministic. Supersession is **declared** (`supersedes: ADR_DF_003`), replacing Graphiti's LLM-mediated temporal invalidation with a dictionary update. |
| FEAT-MEM-03 | Deterministic writer — typed payload → store records; stable UUIDs from natural keys; embed-on-write; idempotent upsert | Zero-LLM write path for structured content. Dedup becomes a key lookup, not a model judgement (the §9.8 failure class is eliminated by construction). |
| FEAT-MEM-04 | Relay integration — MEMORY stream consumer (FastStream handler): `structured_json` → writer; `markdown`/`text` → chunk+embed | Connects capture to storage. The drain worker moves here (supersedes relay D4) because the writer it calls lives here; nats-infrastructure keeps stream definitions only. |
| FEAT-MEM-05 | Retrieval API + context assembly — `search(project, filters, query, token_budget)`; port of guardkit's job-specific context semantics; coverage scoring hook | The read side the thesis is judged on. Metadata filters + vector similarity + token budgeting — deterministic, auditable. |
| FEAT-MEM-06 | MCP server module — FastMCP exposing search/write tools, replacing the Graphiti MCP for Claude Desktop sessions | Keeps the Desktop planning workflow first-class. Patterns lifted from `fastmcp-python` template as reference, not a re-init. |
| FEAT-MEM-07 | Re-index + Fable backfill — guardkit seeds/ADRs through the writer from markdown; one-time Fable 5 job structuring genuinely unstructured legacy docs into typed payloads | Populates the store from authoritative source (ADR-SP-007 made this free). The backfill is the only frontier-model job in the phase — authored once, inside the window, never needed again. |
| FEAT-MEM-08 | GuardKit read-path cutover — coach context, feature-plan context, and CLI retrieval pointing at fleet-memory | **The GROI fix.** Retrieval integrations are first-class deliverables this time, not the afterthought that left 0/10 paths proven. Cross-repo (guardkit). |
| FEAT-MEM-09 | Cutover + decommission runbook — preload change, Gemini fallback deletion, Graphiti freeze, stream-vs-store audit | The 28GB reclaim and the clean ending. Runbook in `docs/runbooks/` in house style (phased, PASS/FAIL gates, rollback, what-NOT-to-do). |

## Success criteria

The phase succeeds when, with the store populated and guardkit cut over:

1. **Retrieval parity.** On a fixed probe set of ≥15 real job-context queries (drawn from coach-context and feature-plan-context usage), fleet-memory returns the relevant ADR/pattern/warning in the token budget at least as often as Graphiti on the frozen pre-cutover graph. (Floor: parity. Aspirational: wins on filter precision.)
2. **Zero-LLM structured writes.** 100% of typed-payload writes complete with no LLM call, measured at the serving layer (no `qwen-graphiti` traffic during re-index of structured content).
3. **Zero capture loss.** Stream-vs-store audit over the soak: every `MemoryEpisodeV1` published is either ingested or in DLQ with a recorded reason. No silent losses — the failure mode that started all of this.
4. **28GB reclaimed.** `qwen-graphiti` out of the always-on preload; steady-state GB10 memory during interactive hours reduced accordingly; Gemini fallback config deleted (£0 cloud on the memory path).
5. **Reads are connected.** Coach context and feature-plan context demonstrably retrieve from fleet-memory in real pipeline runs (history files as evidence) — the explicit anti-GROI criterion.
6. **Re-index is cheap.** Full guardkit re-index from markdown completes in minutes, not hours, and is idempotently re-runnable — proving the recovery/migration story.

## Out of scope

| Concern | Why deferred |
|---|---|
| LLM extraction of unstructured episodes | Chunk+embed ships in this phase; raw episodes persist in MEMORY stream, so batch enrichment remains possible later without re-capture. Extraction returns only if retrieval gaps demand it (recorded against criteria 1). |
| Trace proxy / MEMORY_TRACES (relay D8/P5) | Its purpose was a training corpus for a distilled *extraction* model; with extraction off the write path, it's demoted to optional. Revisit if extraction returns. |
| Hindsight evaluation | Solves conversation-memory — the slice explicitly deferred. Killed as a decision input. |
| TASK-REV-7BFP / TASK-REV-VLLW experiments | On hold; they optimized the cost of a model whose job is being eliminated. 7BFP survives only as contingency if extraction returns. |
| AWS leaf-node deployment of capture (study-tutor in eu-west-2) | Architecture validated (leaf + sourced stream); build follows the relay landing, not inside this window. |
| Client-account (FINPROXY) memory isolation | Relay scope O1 stays deferred — revisit when a client needs isolated memory. |
| Read replica / mirrored index in the VPC | Known solution to a problem we don't have yet (cloud agents tolerating home-link reads). |
| jarvis/forge/specialist-agent publisher integrations | The nats-core publisher makes these one-call adds; guardkit is the exemplar in-window, fleet rollout follows. |
| Graphiti data export | Nothing to rescue — ADR-SP-007. The frozen graph is kept read-only through soak purely as a comparison baseline, then archived. |

## Architectural constraints (must NOT be violated)

- **DECISION-DF-001.** No cloud API on the dark-factory critical path. Fable 5 is used for *authoring* (planning sessions, one-time backfill content) — never wired into runtime ingestion or retrieval.
- **ADR-SP-007 carried forward.** Markdown stays authoritative; the store is an index. Any "fix the data" instinct routes to fixing the source document and re-indexing.
- **Relay contract frozen.** `MemoryEpisodeV1` is framework-neutral (relay D7) and versioned; fleet-memory adapts to it, never the reverse. Engine-specific mapping lives in this repo's services.
- **Template invariants.** Handler → Service unidirectional flow; schemas in the Schemas layer; `TestNatsBroker` for messaging tests; lifespan-managed Postgres pool; pydantic-settings configuration. No architectural freelancing inside the template's layers.
- **Underscores everywhere.** `fleet_memory` package, Postgres schema/identifiers, namespace tuples, group identifiers. Hyphens confined to the repo name. (FalkorDB scar tissue; carried as fleet convention.)
- **Idempotency at two layers.** `Nats-Msg-Id` dedupe window at JetStream + natural-key upsert at the writer. At-least-once delivery is assumed, double-write is impossible by construction.
- **Review before fix.** Any retrieval-quality miss during soak gets a review task with root cause before any schema or index change.

## Status snapshot — 2026-06-12

| Item | Status |
|---|---|
| Repo init from `nats-asyncio-service` | ✅ Done |
| Capture hook + settings.json + .gitignore | ✅ Wired 2026-06-12 |
| Memory Relay scope (nats-infrastructure) | ✅ Authored 2026-06-12; D4 superseded by FEAT-MEM-04 placement |
| TASK-REV-7BFP / TASK-REV-VLLW | ⏸️ On hold (see Out of scope) |
| Phase CORE scope + build plan | ✅ This pair |
| FEAT-MEM-01..09 | ⬜ Not started — prefilled spec commands in the build plan |
| Fable 5 window | 🕐 ~10 days from 2026-06-12 |

---

*Scope authored 12 June 2026 as the canonical `phase-N-scope.md` + `phase-N-build-plan.md` pair, aligning fleet-memory with the GuardKit workflow used in sibling repos (specialist-agent, forge, study-tutor, jarvis, agentic-dataset-factory). Supersession of Memory Relay decisions is recorded in the build plan's Resolved Decisions table.*
