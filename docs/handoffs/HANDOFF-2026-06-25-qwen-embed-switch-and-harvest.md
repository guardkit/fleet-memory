# HANDOFF — Qwen embed switch → guardkit harvest (2026-06-25)

Resumable handoff for a fresh session. The post-Graphiti **memory write path is LIVE and verified** on the
GB10 (`promaxgb10-41b1`). Two things remain to "run the harvest on the GB10": **(1) switch the embedder to
Qwen3-Embedding-0.6B/1024 (surgically)**, then **(2) run the guardkit harvest (FEAT-HARV)**. This doc carries
the adversarially-verified procedure so step 1 doesn't take down the rest of the box.

## TL;DR

- **Live now:** broker `ships-computer-nats`, relay `fleet-memory-relay` (durable consumer bound), NAS
  Postgres+pgvector, embedder = **nomic/768** on llama-swap `:9000`. Store is **empty** (0 rows).
- **Next:** switch the relay's embedder to **Qwen3-Embedding-0.6B (served as model `embed`, 1024-dim)** —
  **SURGICALLY** (add only the `embed` block; do NOT run the full single-spark bring-up on this box).
- **Then:** `/feature-build FEAT-HARV` (guardkit) → `guardkit memory harvest` → FEAT-MEM-07 re-index →
  FEAT-MEM-05 parity eval vs Graphiti → FEAT-MEM-08 cutover → FEAT-MEM-09 decommission.

## Repo state (all pushed unless noted)

| Repo | HEAD | What landed this session |
|---|---|---|
| nats-core | `d1f421e` | P1 publisher (unchanged this session) |
| nats-infrastructure | `5c3b8df` | `fleet-memory` relay user (FEAT-MEM-04) + `guardkit` publisher user (P4) + test fixes |
| fleet-memory | `77f71fb` | episode_type schema fix, FastStream 0.7 compat, **containerized relay** (`deploy/relay/`), FEAT-MEM-04 complete + reconciled, `RUNBOOK-qwen-embed-switch.md` |
| guardkit | P4 brief pushed (`65dd2276`) | P4 `--context` brief + `FEAT-HARV` planned (`.guardkit/features/FEAT-HARV.yaml`). NOTE: repo had 1 unrelated `test(coach)` commit ahead of origin |
| dgx-spark | `ce7fa11` | embed ctx comment fix |

## Why this matters (the strategy, in one paragraph)

Graphiti (FalkorDB-backed, LLM `qwen-graphiti` on its write path: ~28 GB always-on, £30/weekend fallback,
0/10 high-value paths) is being **decommissioned**. fleet-memory replaces it with deterministic, LLM-free
writes to Postgres+pgvector. You **re-harvest from source docs** rather than copy FalkorDB→Postgres because
(a) the data models differ (LLM-extracted graph vs. deterministic doc chunks), (b) the goal is to shed the
LLM-derived content, and (c) embeddings must be regenerated anyway (the model is changing nomic→Qwen).
Authoritative: `nats-infrastructure/docs/design/specs/memory-relay/memory-write-path-v2-post-graphiti.md`;
embedder decision: `guardkit/docs/decisions/DECISION-DF-004-...md` §2.1 (Qwen3-Embedding-0.6B, **1024-dim**).

---

## STEP 1 — switch the embedder (SURGICAL). Adversarially verified 2026-06-25.

> ⛔ **DO NOT run the full single-spark bring-up (`dgx-spark/RUNBOOK-single-spark-bring-up.md` Phase 3.2) on
> this box.** It overwrites `/opt/llama-swap/config/config.yaml` with the 5-model public config and **deletes
> 38 resolvable model names**, breaking live containers that hard-code them: `graphiti-mcp` (`qwen-graphiti` +
> `nomic-embed`), `forge-prod` Graphiti (active `.guardkit/graphiti.yaml`), `specialist-agent-architect`
> (`architect-agent`), `study-tutor` (`gemma4-tutor`), the granite vision/docling stack, **and** the relay.
> The surgical path below isolates the blast radius to the relay alone.

The `embed` serving spec to copy is the `embed` block in `dgx-spark/examples/llama-swap-config.public.yaml`
(`--embedding --pooling last`, 1024-dim — last-token pooling is a Qwen3-Embedding requirement). Ordered:

**0. Back up ALL FOUR state surfaces** (config-only is NOT enough):
```bash
sudo cp /opt/llama-swap/config/config.yaml ~/config.live.bak
cp ~/Projects/appmilla_github/fleet-memory/deploy/relay/.env.deploy ~/relay.env.deploy.bak   # gitignored — only copy
# Note the ORIGINAL triplet: served=nomic-embed/768, FLEET_MEMORY_EMBED_DIMS=768 (unset/default), store_vectors=vector(768)
export FLEET_MEMORY_PG_DSN="postgresql://fleet_memory:<PW>@whitestocks.tailebf801.ts.net:5433/fleet_memory"  # PW in deploy/nas/.env.deploy
```
**1. Confirm the store is still empty** (the whole low-risk premise):
```bash
psql "$FLEET_MEMORY_PG_DSN" -c "select count(*) from store;"   # MUST be 0 — if not, STOP (it's a full re-embed, not a rebuild)
```
**2. Stop the relay FIRST** (collapses the DLQ danger window to zero; un-acked episodes redeliver later):
```bash
cd ~/Projects/appmilla_github/fleet-memory/deploy/relay && docker compose stop
```
**3. Serve `embed` surgically** — copy ONLY the `embed` block into the live `/opt/llama-swap/config/config.yaml`,
keeping `nomic-embed` (graphiti-mcp/forge still need it). **⚠️ Strip the `embeddings` alias** from the new
block — live `nomic-embed` already owns it (duplicate-alias collision); the relay only ever calls the literal
`embed`. Restart llama-swap.
**4. Confirm `embed` serves 1024 BEFORE touching the relay env** (it is NOT served right now):
```bash
curl -s http://127.0.0.1:9000/v1/models | grep -o embed
curl -s http://127.0.0.1:9000/v1/embeddings -H 'content-type: application/json' \
  -d '{"model":"embed","input":"dim check"}' | python3 -c "import sys,json;print('dim=',len(json.load(sys.stdin)['data'][0]['embedding']))"   # expect dim= 1024
```
**5. Point the relay at it** — edit `deploy/relay/.env.deploy` (chmod 600), add:
```
FLEET_MEMORY_EMBED_MODEL=embed
FLEET_MEMORY_EMBED_DIMS=1024
```
**6. Drop ALL FOUR tables while the relay is stopped** (`vector_migrations` gates the `CREATE` — if it
survives, the column is never rebuilt at 1024):
```bash
psql "$FLEET_MEMORY_PG_DSN" -c "DROP TABLE IF EXISTS store_vectors, vector_migrations, store, store_migrations CASCADE;"
```
**7. Recreate the relay** (re-reads `.env.deploy`; `store.setup()` rebuilds the schema at vector(1024)):
```bash
docker compose up -d --force-recreate && docker compose logs -f   # expect "FastStream app started successfully!"
```
**8. Verify the triplet before trusting writes:**
```bash
psql "$FLEET_MEMORY_PG_DSN" -c "\d store_vectors" | grep embedding            # vector(1024)
# publish one probe episode (as rich or guardkit), then:
psql "$FLEET_MEMORY_PG_DSN" -c "select count(*) from store;"                   # >= 1
nats stream subjects MEMORY 'memory.dlq.>'                                     # EMPTY (no EmbedDimensionError)
# clean up probe rows + purge the stream afterward
```
**9. Rollback** (only clean while store is empty — re-check count=0): restore `~/config.live.bak` + restart
llama-swap; restore `~/relay.env.deploy.bak` (or delete the two EMBED lines → defaults nomic/768); stop relay,
re-drop the four tables, `up -d --force-recreate` → vector(768). **A config-only restore reproduces the
768-vs-1024 DLQ failure.**

Full operational detail (with the verified corrections): `fleet-memory/deploy/relay/RUNBOOK-qwen-embed-switch.md`.

## STEP 2 — run the harvest (FEAT-HARV)

After the embedder is on Qwen/1024 and verified: from the guardkit repo, `/feature-build FEAT-HARV`, then the
live run `guardkit memory harvest [--dry-run]`. It publishes guardkit's curated `.md` artifacts as
`MemoryEpisodeV1` via `nats_core.publish_episode`, connecting as the **`guardkit`** NATS user (provisioned,
publisher-only; password in `nats-infrastructure/.env` `GUARDKIT_NATS_PASSWORD`). Brief + connect details:
`guardkit/docs/design/specs/memory-publisher/P4-harvest-publisher-feature-brief.md`. Verify rows landed with a
`select … from store where prefix like 'fleet_memory.guardkit%'`.

Then: FEAT-MEM-07 re-index → FEAT-MEM-05 parity eval vs Graphiti baseline → FEAT-MEM-08 cutover → FEAT-MEM-09
decommission. **Lock the embedder (Qwen/1024) before the FEAT-MEM-05 parity eval** — it drives retrieval
quality, so evaluate the store as it will actually run.

## Gotchas / hard-won facts

- This box `promaxgb10-41b1` runs the broker, the relay, AND the `:9000` llama-swap the relay embeds against —
  the embedder switch is a live op, not a sandbox. Other live consumers of `:9000`: graphiti-mcp, forge,
  specialist agents, study-tutor (see the full-bring-up blocker above).
- The relay container reads `FLEET_MEMORY_EMBED_MODEL` (default `nomic-embed-text-v1.5`) and `EMBED_DIMS`
  (default 768) from `deploy/relay/.env.deploy`; it calls OpenAI `/v1/embeddings` (`src/fleet_memory/embed.py`),
  and `EmbedDimensionError → poison` DLQs every episode on any dim mismatch (`relay/service.py`).
- Broker rebuilds need `docker compose up -d --build` (entrypoint baked into the image); the relay + forge
  auto-reconnect across it.
- Saved project memories: `feat-harv-p4-harvest-publisher`, `qwen-embed-switch-1024` (in the agent memory dir).

## Key references

- Corrected switch procedure: `fleet-memory/deploy/relay/RUNBOOK-qwen-embed-switch.md`
- Relay deploy: `fleet-memory/deploy/relay/` (Dockerfile + compose + README)
- P4 brief: `guardkit/docs/design/specs/memory-publisher/P4-harvest-publisher-feature-brief.md`
- Embedder decision: `guardkit/docs/decisions/DECISION-DF-004-...md` §2.1
- Bring-up runbooks (for the actual DGX Spark / clean box, NOT this live box): `dgx-spark/RUNBOOK-single-spark-bring-up.md`, `RUNBOOK-two-spark-bring-up.md`
- Authoritative design: `nats-infrastructure/docs/design/specs/memory-relay/memory-write-path-v2-post-graphiti.md`
- Prior handoff (write-path bring-up): `fleet-memory/docs/handoffs/HANDOFF-2026-06-25-memory-write-path-gb10.md`
