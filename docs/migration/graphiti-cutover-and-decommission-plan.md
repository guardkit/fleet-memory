# Graphiti → fleet-memory: cutover (FEAT-MEM-08) + decommission (FEAT-MEM-09) plan + consumer inventory

> **Status:** DRAFT for review (2026-06-27). Companion to
> `docs/handoffs/HANDOFF-2026-06-27-harvest-recovery-and-graphiti-cutover.md`.
> Goal the operator cares about: **retire `qwen-graphiti` (Qwen2.5-14B-Instruct)**
> so the spark bring-up is the clean all-open lineup. That model exists only to
> power Graphiti's extraction → **removing it ≡ decommissioning Graphiti**.

---

## 0. Where we stand (one screen)

- fleet-memory is **built + deployed**; the 447-episode guardkit corpus is **loaded** (TASK-HARV-007 ✅).
- **Next gate:** FEAT-MEM-05's parity-eval harness is built but **not yet run** against the loaded corpus. Cutover should not start until parity holds.
- **fleet-memory is pure embeddings** (no instruct LLM). Its public replacement surface:
  - **MCP server** — `python -m fleet_memory.mcp` (stdio), 3 tools: `memory_search`, `memory_write_payload`, `memory_supersede`; resource `memory://projects`.
  - **Write paths** — NATS publish `MemoryEpisodeV1` to `memory.episode.{project_id}.{episode_type}` (prose → chunk+embed; JSON → typed payload); or the `memory_write_payload` MCP tool; or `DeterministicWriter` in-proc.
  - **7 typed payloads** — `adr`, `review_report`, `build_outcome`, `pattern`, `warning`, `seed_module`, `document`; natural key `type:project:identifier`; `domain_tags` facets; `supersedes` links.
  - **Config** — `FLEET_MEMORY_*` env (PG DSN, EMBED_URL/MODEL/DIMS, NATS_URL). No LLM config.
- **Graphiti's 5 consumers**: guardkit (the big one) + forge, jarvis, specialist-agent, study-tutor. **All four downstream consumers are SOFT dependencies** (fire-and-forget writes, reads degrade to empty) and **all already depend on `nats-core`**.

## 1. The one thing to internalise before planning

**This is not a 1:1 API swap.** Graphiti and fleet-memory are different retrieval models:

| | Graphiti (now) | fleet-memory (target) |
|---|---|---|
| Write | `add_episode(text)` → **LLM extracts** entities + relationships into a graph | publish/`write_payload` → **deterministic** chunk+embed or typed upsert (no LLM) |
| Read | `search(query)` → hybrid graph search, reranked → **facts / edges** | `memory_search(project, query, …)` → vector search → **one token-budgeted context block** |
| Identity | `group_id` (28 system+project groups) | `project` + `payload_type` + `domain_tags`; natural key |

**Implications:**
- A **write-only** consumer (audit trail) migrates trivially — just republish to a fleet-memory topic.
- A consumer that **reads graph facts and reasons over edges** must either accept a flat context block, or keep richer structure in typed payloads. The **parity eval is the gate** that tells you whether the vector context is good enough for guardkit's job-specific reads.
- guardkit writes **free-text** episodes (`add_memory` to `guardkit__task_outcomes`); fleet-memory prefers **typed payloads**. The cutover must decide a mapping (below).

---

## 2. FEAT-MEM-08 — guardkit read/write cutover

**Goal:** guardkit's knowledge **writes** (task outcomes, decisions, ADRs, doc seeding) and **reads** (coach context, feature-plan context, CLI search) go to fleet-memory instead of Graphiti — and the reads **demonstrably fire in real pipeline runs** (the GROI anti-criterion: don't just build a client, wire it in and prove it).

### 2a. Write-side mapping

| guardkit write (today) | Source | fleet-memory target | Decision |
|---|---|---|---|
| Task outcome → `guardkit__task_outcomes` (free text) | `/task-complete` Tier-0 `mcp__graphiti__add_memory`; Tier-1 `guardkit graphiti capture-outcome`; `outcome_manager.capture_task_outcome` | **`build_outcome`** typed payload (task_id→identifier, status, duration, + lessons/approach in body) **or** a prose `document` episode | **Recommend typed `build_outcome`** (structured retrieval). May need 1–2 extra fields on the type. |
| Architectural decision → `guardkit__project_decisions` | `/task-complete` Tier-0 write 2; `adr_service` | **`adr`** payload (decision, status, rationale, supersedes) | Direct, clean fit. |
| ADRs (feature-build) | `cli graphiti seed-adrs`, `adr_service` | **`adr`** payload | Direct. |
| Docs / feature-specs / context files | `cli graphiti add-context` | **reindex pipeline** (already FEAT-MEM-07) → `document`/typed | Largely already covered by the harvest; fold `add-context` into `guardkit memory` reindex. |
| System seeding (product_knowledge, command_workflows, …) | `cli graphiti seed`, `seed-system` | **`document`/`seed_module`** payloads under a `guardkit_system` project, **or drop** | **Decision:** is seeded system knowledge still needed once the corpus is harvested? Much overlaps the harvest. Candidate to **retire**, not migrate. |

> **group_id → fleet-memory mapping is the core design task.** guardkit's 19 system + 9 project groups collapse onto fleet-memory's (`project`, `payload_type`, `domain_tags`). Most project groups → `project="guardkit"` + a `payload_type`/`domain_tag`; system groups → a `guardkit_system` project or `domain_tags`. Produce this mapping table first; it drives everything.

### 2b. Read-side mapping

| guardkit read (today) | fleet-memory target |
|---|---|
| `cli graphiti search` / `show` / `verify` / `status` | new `guardkit memory search` over `memory_search` tool / retrieval API |
| Coach context builder, feature-plan context (the GROI reads) | `memory_search(project="guardkit", query=…, payload_types=…, token_budget=…)` → context block injected into the prompt |
| `graph_stats` / topology | not reproduced (vector store has no graph topology); drop or replace with store counts |

### 2c. Integration mechanism (least-churn approach)

1. **Adapter, not rewrite.** Add a `guardkit/knowledge/fleet_memory_client.py` that exposes the **same shape** guardkit call-sites already use (`add_episode`→publish/`write_payload`, `search`→`memory_search`), so `graphiti_client.py` call-sites change by swapping the factory, not every caller. `init_graphiti()`/`get_graphiti()` gains a fleet-memory branch behind a config flag.
2. **`.mcp.json`** — point the memory MCP server at fleet-memory: replace the graphiti HTTP entry (`http://promaxgb10-41b1:8004/mcp`) with the fleet-memory stdio server (`python -m fleet_memory.mcp`, `FLEET_MEMORY_*` env). Tool names in `/task-complete` change `mcp__graphiti__add_memory` → `mcp__fleet_memory__memory_write_payload`, `mcp__graphiti__search_*` → `mcp__fleet_memory__memory_search`.
3. **CLI** — fold into the existing `guardkit memory` group (it already has `harvest`): add `search`, `capture-outcome`, `status`. Keep `guardkit graphiti …` as a **deprecated alias** that warns + delegates during the soak.
4. **Config** — `.guardkit/graphiti.yaml` → `.guardkit/fleet-memory.yaml` (PG DSN, embed URL/model/dims, NATS URL; **no LLM block**). Leave `graphiti.yaml` with `enabled: false` during soak for rollback.
5. **`/task-complete`** — repoint Tier-0 to `memory_write_payload` (build_outcome + adr), Tier-1 to `guardkit memory capture-outcome`. Keep the non-blocking posture and the response-parser defence (now trivial — no group override on fleet-memory).

### 2d. Proposed waves
1. **W1 — mapping + adapter**: the group_id→payload mapping table; `fleet_memory_client.py` adapter + config; unit tests. (No behaviour change yet.)
2. **W2 — writes**: repoint `/task-complete` + `outcome_manager` + `adr_service` to fleet-memory (dual-write to both during soak, behind a flag, for the parity audit).
3. **W3 — reads (GROI)**: wire `memory_search` into the coach-context / feature-plan readers and **prove a real run reads from fleet-memory** (log evidence; this is the anti-criterion that sank prior "reads exist on paper" attempts).
4. **W4 — CLI + cleanup**: `guardkit memory search/status`, deprecate `guardkit graphiti`, docs/rules update.

### 2e. Risks / open decisions
- **Typed vs prose** for task outcomes (recommend typed `build_outcome`).
- **Retrieval parity** must pass first (FEAT-MEM-05) — if the flat context block underperforms graph facts for some job, that feeds back to retrieval design, *not* to unfreezing Graphiti.
- **Seeded system knowledge** — migrate vs retire (recommend retire what the harvest already covers).
- **Dual-write soak** to audit "every Graphiti write also lands in fleet-memory" before cutting reads over.

---

## 3. Per-consumer inventory (forge · jarvis · specialist-agent · study-tutor)

**All four: SOFT dependency (won't crash without Graphiti), `nats-core` already present, same FalkorDB+`qwen-graphiti` backend.** So decommission won't break them — the choice per consumer is **migrate (preserve learning)** vs **stateless-interim (lose learning until they migrate on their own timeline)**.

| Consumer | Uses Graphiti for | Touchpoints | Read path? | Recommendation | Effort |
|---|---|---|---|---|---|
| **forge** | cross-build learning: gate decisions, calibration events, session outcomes (`forge_pipeline_history`, `forge_calibration_history`); reads **priors** | `memory/writer.py:250 add_episode`; `memory/priors.py:704 search`; `reconciler.py:458 search` | **YES** (priors drive calibration) | **Migrate** — highest learning value. Write `build_outcome`/`pattern` payloads via NATS; read priors via `memory_search`. | **M** |
| **jarvis** | routing/dispatch **audit** history (`jarvis_routing_history`) | `infrastructure/routing_history.py:731,935 add_episode` (write-only) | No (write-only audit) | **Trivial**: republish to fleet-memory NATS topic, *or* drop (audit, not learning). | **S** |
| **specialist-agent** | role learning: `SessionMetrics`, role knowledge (`role:{role_id}`) | `knowledge/writer.py:196 add_memory`, `:248 search_nodes` (MCP callables) | Yes (role knowledge) | **Migrate or stateless**: swap MCP callables to fleet-memory `memory_write_payload`/`memory_search`; `role:{id}` → `project` or `domain_tag`. | **S–M** |
| **study-tutor** | learner model: session completion, topic-confidence, misconceptions (`student-{id}` partitions) | `knowledge/async_write.py:437 add_episode`; `knowledge/queries.py` partition reads + `search_nodes` fallback | **YES** (per-learner state) | **Migrate** (real learner state worth keeping) — but it's a **separate product on its own timeline**; `student-{id}` → `project` partition. | **M** |

**Common migration shape (identical for all):** replace `add_episode()` with a NATS publish of `MemoryEpisodeV1` (they all have `nats-core`); replace reads with `memory_search`/store queries keyed by the same partition; drop the `qwen-graphiti`/LLM config. Because the writes are already fire-and-forget, this can be done **incrementally and independently per repo** without coordination.

---

## 4. FEAT-MEM-09 — Graphiti decommission (drop `qwen-graphiti`)

### 4a. The precondition decision (this is the operator's call)

- **Option A — wait for all 5.** All consumers migrated → **zero learning loss**, but gated on the slowest (study-tutor, a separate product). Longest path.
- **Option B — guardkit-first (recommended).** Once **guardkit is cut over + parity holds**, decommission Graphiti and let forge/jarvis/specialist-agent/study-tutor run **stateless-interim** (they're soft — they don't crash, they just lose cross-session learning) and migrate on their own schedules. **Unblocks the Qwen2.5 removal immediately.**

The earlier framing called the other 4 a "blocker." Because they're **soft**, they're a blocker only under Option A. Under Option B they're a **follow-on**, and `qwen-graphiti` can go as soon as guardkit is off it.

### 4b. Steps (once the precondition is met)
1. **Soak**: dual-write guardkit (FEAT-MEM-08 W2) for N days; audit **published == stored** so nothing is lost vs Graphiti.
2. **Freeze** FalkorDB read-only; run a stream-vs-store / graph-vs-store audit for guardkit's groups.
3. **Pull the model**: remove `qwen-graphiti` from llama-swap `hooks.on_startup.preload` and the `qg` matrix-var (and from every set — it's in `all`/etc.). Set `enabled: false` / remove the LLM block in each consumer's `graphiti.yaml`.
4. **Keep `nomic-embed`** for now — forge + LPA still use it; only `qwen-graphiti` (Qwen2.5) is being retired here. (nomic leaves only when forge/LPA also move off it.)
5. **Runbook/config**: the public runbooks already exclude Qwen2.5; the personal config drops the `qwen-graphiti` block → this *is* Appendix B's "pure headroom" end-state. Delete `/opt/llama-swap/models/qwen2.5-14b/` after soak to reclaim disk.
6. **Archive** FalkorDB (export + park) after the soak proves no regression.

### 4c. Rollback
Until step 6, rollback = re-enable `qwen-graphiti` preload + flip the consumers' `graphiti.yaml` back to `enabled: true`. The dual-write window means no guardkit capture is lost either way.

### 4d. The payoff
`qwen-graphiti` gone → VRAM freed, the reference box matches the all-open public lineup, and the single/two-spark bring-up videos can be recorded against the exact committed config.

---

## 5. Recommended sequence

1. **Run FEAT-MEM-05 parity eval** against the loaded 447-episode corpus (lock the Qwen3/1024 embedder first). **Gate.**
2. **File + build FEAT-MEM-08** (guardkit cutover) — start with the **group_id→payload mapping table** and the **adapter**; dual-write; then wire the **reads into a real run** (GROI).
3. **Decide Option A vs B** for decommission (recommend **B**).
4. **File + build FEAT-MEM-09** — soak → freeze → pull `qwen-graphiti` → archive. Record the runbook videos.
5. **Follow-on**: migrate forge → jarvis → specialist-agent → study-tutor off Graphiti on their own timelines (each is independent, soft, NATS-ready).

> **If the goal is just the public videos:** none of this blocks them — the public config has no Qwen2.5 today. This plan is the path to retiring it from the **reference box**.
