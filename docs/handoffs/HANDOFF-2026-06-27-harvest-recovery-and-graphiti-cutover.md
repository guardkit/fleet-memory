# HANDOFF — harvest recovery (in progress) + Graphiti→fleet-memory cutover / Qwen2.5 removal (2026-06-27)

Resumable handoff for a fresh session. Runs **on the box `promaxgb10-41b1`**
(relay, broker `127.0.0.1:4222`, Postgres-over-Tailscale, and the `:9000`
llama-swap are all local). Picks up from
`HANDOFF-2026-06-26-harvest-recovery.md` and the RELAYDROP01-fix validation.

> A prior session is still **monitoring the live harvest drain to completion**
> (background poller + this session will verify + close TASK-HARV-007 when
> `pending=0`). This doc exists so the *conversation* (esp. the Graphiti
> decommission / Qwen2.5-removal planning) can continue in a new session in
> parallel. **Do not start a second relay replay** — one is already running.

> ## ✅ UPDATE 2026-06-27 (end of session) — harvest COMPLETE, loose ends committed
>
> - **Harvest recovery DONE: 447/447 distinct episodes** stored at dim 1024
>   (`store_vectors` = 2846 chunks, store rows = distinct keys = vectors → no dups),
>   DLQ purged + empty, consumer drained (`redelivered=0`). **TASK-HARV-007 →
>   `completed`** (both task copies, all 6 ACs ticked).
> - **fleet-memory ack/timeout fix COMMITTED** (`TASK-FIX-RELAYACKTMO01`): `ack_wait`
>   settings-driven (1200s) + `embed_timeout_s` 180s + tests. (`.env.deploy` stays
>   gitignored — values documented in it.)
> - **dgx-spark runbook UPDATED + committed** (`TASK-LLSWAP-EMRESIDENT01` AC-2): the
>   coexistence-set rule is in §3.2, the gotcha table, and Appendix B's migration note.
>   Still open: folding the live `em`-in-every-set edit into the *canonical personal
>   config* once `MIGRATION.md` brings it into the repo (AC-1).
> - The relay is left running (drained, idle, healthy) on the fixed image with
>   `embed` pinned resident.
>
> **The rest of this doc (the migration roadmap + the Qwen2.5 decision) is still the
> live agenda for the next session.** The data load is done; FEAT-MEM-05 parity eval
> is the next gate.

---

## TL;DR

1. **The RELAYDROP01 fix is validated** (53 unit + 2 real-store Docker integration
   tests; plus observed live — embed timeouts went to the DLQ, not silently
   dropped). The titular goal of the prior handoff is **done**.
2. **The 167→447 recovery is in progress** (~329/447 distinct episodes at
   2026-06-27 12:47, climbing cleanly, `redelivered=0`). ETA ~2–3h from then.
3. Two **new root causes** beyond the original three fixes were found and
   **actioned this session** (not just noted):
   - **embed cold-start (85–181s) on the shared `:9000`** because qwen3 `embed`
     was only in the `all` llama-swap matrix-set → evicted by finproxy/granite,
     tutor, arch. **Fixed by pinning `embed` resident** (added to lpa/lpa_v3/
     tutor/arch).
   - **`ack_wait=60s` too short for large multi-chunk episodes** (a 70+-chunk
     episode embeds+writes every chunk before the ack → ack_wait expires →
     redeliver/reprocess forever). **Fixed by making `ack_wait` settings-driven
     (default 1200s) + raising `embed_timeout_s` 10→180s.**
4. **Two follow-up tasks drafted** (both actioned, not noted) — see below.
5. **Big picture:** fleet-memory is built + deployed; what remains is finish the
   data load (this harvest) → parity eval → **guardkit cutover (FEAT-MEM-08, not
   filed)** → **Graphiti decommission (FEAT-MEM-09, not filed)**. **Dropping
   Qwen2.5 ≡ decommissioning Graphiti**, and Graphiti has **5 consumers**
   (guardkit, forge, jarvis, specialist-agent, study-tutor) — so full Qwen2.5
   removal is bigger than just guardkit. **Open decision for the operator at the
   end of this doc.**

---

## State (verified 2026-06-27 ~12:47)

| Thing | State |
|---|---|
| relay container | **fixed image** (`built 2026-06-27T08:14`), running, healthy |
| relay code | RELAYDROP01 + RELAYBATCH01 + EMBEDCTX01 + **new ack/timeout fix** (uncommitted working tree) |
| consumer `fleet-memory-relay` | DeliverAll, **`ack_wait=1200s`**, `max_deliver=5`, `redelivered=0` |
| store (distinct guardkit episodes) | **~329 / 447** and climbing |
| store_vectors (chunks) | ~1734, all **dim 1024** |
| MEMORY stream | 447 episode msgs (seq 19–465) + 15 dlq msgs = 462 total |
| DLQ `memory.dlq.guardkit` | **15 stale** (from the first 10s-timeout pass; their episodes are being re-stored by the current pass — purge after verify) |
| embed (`:9000`) | qwen3 `embed`/**1024**, **pinned resident** in fleet sets, warm (~20ms) |

---

## Changes made THIS session (so they are not lost or re-done)

### 1. Relay rebuilt on the fixed image
`cd fleet-memory/deploy/relay && docker compose up -d --build`. The three prior
fixes (EMBEDCTX01/RELAYBATCH01/RELAYDROP01) were already committed; this just got
them into the running container (the prior handoff's "easy-to-miss" step).

### 2. llama-swap: `embed` pinned resident  (dgx-spark TASK-LLSWAP-EMRESIDENT01)
Edited **`/opt/llama-swap/config/config.yaml`** (backup:
`config.yaml.bak.20260626-harv`); `-watch-config` hot-reloaded it. Added `& em`
to the non-exclusive coexistence sets:
```
lpa:    "gv & qw & ne & em"
lpa_v3: "gv33 & qw & ne & em"
tutor:  "gt & qw & em"
arch:   "aa & qw & em"
```
Left the memory-maxed exclusive sets (`coach31`, `autobuild_go`, `coder_30b`)
alone. Verified embed resident + warm after reload. **This is a LIVE box change;
persistence into the tracked config + runbook is the open dgx-spark task.**

### 3. fleet-memory relay timeout/ack fix  (TASK-FIX-RELAYACKTMO01) — ACTIONED, UNCOMMITTED
Working-tree changes (live on the relay via the rebuild; **not committed**):
- `src/fleet_memory/settings.py`: `embed_timeout_s` default `10.0→180.0`; **new
  `ack_wait_s: int = 1200`** field.
- `src/fleet_memory/relay/handler.py`: `MEMORY_CONSUMER_CONFIG.ack_wait`
  `60 → _ACK_WAIT_S` (= `settings.ack_wait_s`, else 1200).
- `tests/unit/test_settings.py`: default assertions updated + `ack_wait_s >
  embed_timeout_s` invariant. **160 unit tests pass.**
- `deploy/relay/.env.deploy` (gitignored): explicit
  `FLEET_MEMORY_EMBED_TIMEOUT_S=180`, `FLEET_MEMORY_ACK_WAIT_S=1200`,
  `FLEET_MEMORY_MAX_DELIVER=5`.

### 4. Follow-up task docs drafted
- `fleet-memory/tasks/in_review/TASK-FIX-RELAYACKTMO01-...md` (status in_review;
  only open AC is commit/merge).
- `dgx-spark/TASK-LLSWAP-EMRESIDENT01-embed-resident-matrix-sets.md` (persist the
  live llama-swap edit + add the "always-on dependency must be in every
  coexistence set" rule to the bring-up runbook).

---

## How to FINISH the harvest (resume here if the prior session didn't close it)

```bash
cd ~/Projects/appmilla_github/fleet-memory/deploy/relay
DSN=$(grep '^FLEET_MEMORY_PG_DSN=' .env.deploy | cut -d= -f2-)
NURL=$(grep '^FLEET_MEMORY_NATS_URL=' .env.deploy | cut -d= -f2-)
NU=$(echo "$NURL" | sed -E 's#nats://([^:]+):.*#\1#'); NP=$(echo "$NURL" | sed -E 's#nats://[^:]+:([^@]+)@.*#\1#')
NATS=(nats --server nats://127.0.0.1:4222 --user "$NU" --password "$NP")

# 1. Is it drained?
"${NATS[@]}" consumer info MEMORY fleet-memory-relay -j | python3 -c "import sys,json;d=json.load(sys.stdin);print('pending',d['num_pending'],'ack_pending',d['num_ack_pending'])"

# 2. Verify the recovery (TARGET: 447 distinct episodes; store_vectors >> 447; dim 1024)
psql "$DSN" -tAc "select count(distinct value->>'episode_id') from store where prefix like 'fleet_memory.guardkit%';"   # expect 447
psql "$DSN" -tAc 'select count(*) from store_vectors;'
psql "$DSN" -tAc 'select distinct vector_dims(embedding) from store_vectors;'   # 1024 only

# 3. The 15 stale DLQ msgs are from the OLD 10s-timeout pass; their episodes are
#    re-stored by this pass. Once distinct==447, purge them so DLQ is clean:
#    (verify each stale dlq episode_id is now in store FIRST, then:)
"${NATS[@]}" stream purge MEMORY --subject 'memory.dlq.guardkit' -f
"${NATS[@]}" stream subjects MEMORY 'memory.dlq.>'    # expect empty

# 4. AC-007-6 idempotency: the replay already re-upserted the previously-stored
#    episodes with no duplicates (uuid5 chunk keys) — that IS store-level
#    idempotency. A fresh `guardkit memory harvest` re-run is NOT required and
#    would add 447 new stream msgs (publish-dedupe window has long expired).
#    If you want the AC literally: re-run and confirm distinct stays 447.

# 5. Close TASK-HARV-007 in guardkit (tick AC-007-3..6) + /task-complete.
```

If a NEW monster episode ever needs >1200s, raise `FLEET_MEMORY_ACK_WAIT_S` in
`.env.deploy` and recreate the consumer (delete it, relay recreates at the new
value). With embed pinned resident this should not recur.

---

## Open findings (folded into the task follow-ups; NOT yet actioned)

- **Chunker emits oversized chunks.** `chunk_target_tokens=1000` but the
  heading-aware chunker produces ~3000-token sections, which RELAYBATCH01 then
  **truncates** to the 2048-token embed budget → **degraded embeddings** on large
  sections. Fix: hard-split sections to the embed budget. (Affects retrieval
  quality of the harvested corpus — relevant before the parity eval.)
- **Relay embeds+writes a whole episode before acking.** Per-chunk (or bounded-
  batch) commit would cap the ack-window requirement and let partial progress
  survive a restart — a better structural fix than a large `ack_wait`.

---

## BIG PICTURE: Graphiti → fleet-memory, and removing Qwen2.5

**Verified across guardkit / fleet-memory / forge / jarvis / specialist-agent /
study-tutor / dgx-spark / lpa-platform-poc / nats-infrastructure this session.**

### Migration chain status
| Feature | What | Status |
|---|---|---|
| FEAT-MEM-02/03 | typed payloads + deterministic LLM-free writer | ✅ done |
| FEAT-MEM-04 | NATS relay → Postgres+pgvector write path | ✅ done (hardened this session) |
| FEAT-MEM-05 | retrieval API + context assembly + **parity-eval harness** | ✅ built; **harness not yet RUN** |
| FEAT-MEM-06 | Memory MCP server (replaces graphiti-mcp) | ✅ done |
| FEAT-MEM-07 | re-index / harvest pipeline | ✅ merged; **447-episode load = this run, in progress** |
| FEAT-MEM-08 | **guardkit read/write cutover → fleet-memory** | ❌ **NOT FILED** |
| FEAT-MEM-09 | **Graphiti decommission runbook (drop `qwen-graphiti`)** | ❌ **NOT FILED** |

### The Qwen2.5 finding (the crux)
- **fleet-memory is pure embeddings — no instruct LLM at all** (relay / retrieval
  / MCP / re-index only ever call `/v1/embeddings`).
- **Qwen2.5-14B (`qwen-graphiti`) is invoked directly by exactly one thing:
  Graphiti's entity/relationship extraction.** So **dropping Qwen2.5 ≡
  decommissioning Graphiti.**
- **But Graphiti has 5 consumers**: guardkit, **forge, jarvis, specialist-agent,
  study-tutor**. They read/write the Graphiti graph for cross-session learning
  (they don't call Qwen2.5 themselves). You cannot pull `qwen-graphiti` from the
  always-on fleet until all five migrate to fleet-memory or accept going
  stateless / cloud-fallback.
- **The PUBLIC single/two-spark runbooks already EXCLUDE Qwen2.5** — the all-open
  lineup is `workhorse (Qwen3.6-35B) · coach (Gemma-4-26B) · chat (gpt-oss-20b) ·
  embed (Qwen3-Embedding)`; Graphiti/Qwen2.5 is "out of scope, Appendix B /
  personal config." So **recording the public bring-up videos is NOT blocked by
  Qwen2.5 today.** The blocker is the **personal reference box** still preloading
  `qwen-graphiti` because the 5 consumers depend on Graphiti.

### guardkit↔Graphiti cutover surface (what FEAT-MEM-08 must repoint)
- `.guardkit/graphiti.yaml` → fleet-memory config (Postgres DSN + embed URL/model;
  no LLM)
- `.mcp.json` graphiti HTTP server (`promaxgb10-41b1:8004/mcp`) → fleet-memory MCP
- `guardkit/knowledge/graphiti_client.py` → fleet-memory client / thin adapter
- `/task-complete` outcome capture: Tier-0 `mcp__graphiti__add_memory` + Tier-1
  `guardkit graphiti capture-outcome` → fleet-memory equivalents
- `guardkit/cli/graphiti.py` command group → `guardkit memory` group
- group_id namespacing + outcome schema can be reused as-is

### Critical path to "Qwen2.5 gone from the box"
1. **Finish the harvest** (in progress) → 447 in fleet-memory
2. **Run the parity eval** (FEAT-MEM-05 harness, ≥15-query probe set vs Graphiti) — the gate
3. **File + build FEAT-MEM-08** — guardkit cutover (5 integration points above)
4. **Migrate / stateless-retire the other 4 consumers** (forge, jarvis,
   specialist-agent, study-tutor) — **the long pole, not yet planned**
5. **FEAT-MEM-09** — pull `qwen-graphiti` from the llama-swap preload + the `qg`
   matrix-var, freeze FalkorDB, archive

---

## OPEN DECISION FOR THE OPERATOR (the fork that drives next steps)

**Which goal are we optimizing?**

- **(A) Record the public single/two-spark runbook videos** → *unblocked now*;
  the public config has no Qwen2.5. Nothing in the migration blocks this.
- **(B) Retire Qwen2.5 off the reference box entirely** → needs steps 3–5 above,
  and **step 4 (the other 4 Graphiti consumers) is the real project**. Interim
  shortcut: point Graphiti's LLM at the Gemini fallback to drop the *local* load
  — works, but breaks "all-open."

**Pending offer (next session):** draft the **FEAT-MEM-08 (cutover)** and
**FEAT-MEM-09 (decommission)** plans, plus an **inventory of what each of the
other 4 consumers** (forge/jarvis/specialist-agent/study-tutor) needs to drop
Graphiti.

---

## Reference — key paths

- Relay deploy: `fleet-memory/deploy/relay/` (`.env.deploy`, `docker-compose.yml`)
- Relay source: `fleet-memory/src/fleet_memory/{relay/handler.py,relay/service.py,embed.py,settings.py}`
- llama-swap config: `/opt/llama-swap/config/config.yaml` (backup `.bak.20260626-harv`); `/running`, `/v1/embeddings` on `:9000`
- New task docs: `fleet-memory/tasks/in_review/TASK-FIX-RELAYACKTMO01-*.md`, `dgx-spark/TASK-LLSWAP-EMRESIDENT01-*.md`
- guardkit task being closed: `TASK-HARV-007` (`guardkit/tasks/backlog/memory-harvest-publisher/`)
- Prior handoffs: `fleet-memory/docs/handoffs/HANDOFF-2026-06-2{5,6}-*.md`
- Runbooks: `dgx-spark/RUNBOOK-single-spark-bring-up.md`, `RUNBOOK-two-spark-bring-up.md`
- Publisher: guardkit `python -m guardkit.cli.main memory harvest` (NATS user `guardkit`, creds in `nats-infrastructure/.env`)
