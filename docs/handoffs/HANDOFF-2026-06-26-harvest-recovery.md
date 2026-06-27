# HANDOFF — recover the harvest (338 → 447) now the three embed fixes have landed (2026-06-26)

Resumable handoff for a fresh session, **on the box `promaxgb10-41b1`** (the
Claude session runs ON it — `/opt/llama-swap` + `:9000` + the relay + Postgres
are all local; "SSH denied" earlier was just unkeyed self-SSH). Picks up from
`HANDOFF-2026-06-25-qwen-embed-switch-and-harvest.md` and the first harvest's
**partial 338/447** result.

## TL;DR

The Qwen/1024 embedder switch is **done and correct** (embed served 1024, relay on
1024, `store_vectors = vector(1024)`). The first live harvest stored **338/447** —
109 multi-chunk episodes were **silently dropped** (embed `n_ctx` too small + the
relay batched a whole episode's chunks into one over-budget `/v1/embeddings` call +
that deterministic 400 was mis-routed as transient → nacked to death, not DLQ'd).
**All three fixes are now implemented and committed.** What remains is a
**one-shot recovery**: rebuild the relay container with the fixed code, replay the
447 already sitting in the MEMORY stream, verify 447 land, then close TASK-HARV-007
and continue the FEAT-MEM chain.

## State (verified 2026-06-26)

| Thing | State |
|---|---|
| embed serving | `embed`/1024 live on `:9000`; **`--ctx-size 32768 -np 4` → 8192 tok/slot** (EMBEDCTX01 applied + verified) |
| relay env | `FLEET_MEMORY_EMBED_MODEL=embed`, `FLEET_MEMORY_EMBED_DIMS=1024` |
| store | `store` 338 rows, `store_vectors` 338 (1:1 — only single-chunk episodes survived), all dim **1024** |
| MEMORY stream | **447 messages intact** (seq 19–465) — nothing lost at the stream level |
| consumer `fleet-memory-relay` | drained (`Unprocessed: 0`, 296 redeliveries, 109 dropped), `DeliverPolicy` defaults to **ALL** |
| DLQ `memory.dlq.>` | **empty** (proves the 109 were silently dropped by the OLD code, not parked) |
| **relay container** | ⚠️ **running the OLD image** (built `2026-06-25 13:40`, BEFORE the fix commits) — the fixes are in source but NOT in the running relay |

## The three fixes (all `fleet-memory/tasks/completed/`, all committed)

| Task | Commit | What |
|---|---|---|
| `TASK-FIX-EMBEDCTX01` | `a93fc3e` | embed `--ctx-size 8192 → 32768` (kept `-np 4` → 8192 tok/slot; ubatch 8192 = proven mem profile). Verified standalone: 2.4k & 7.2k-tok → 200/1024; 23.9k-tok → 400 (RELAYBATCH01's job). |
| `TASK-FIX-RELAYBATCH01` | `d9484c9` | `embed.py` now **token-bounded sub-batching**: packs chunks into batches under a budget ≤ `n_ctx` instead of one unbounded request. |
| `TASK-FIX-RELAYDROP01` | `abe48c3` | deterministic `exceed_context_size_error` → `PoisonEpisodeError` → DLQ; **max-deliver exhaustion now → DLQ + term** (handler.py:169-170), never silently dropped. |

## RECOVERY — ordered, do this on the box

### 0. Pre-checks
```bash
cd ~/Projects/appmilla_github/fleet-memory
DSN=$(grep '^FLEET_MEMORY_PG_DSN=' deploy/relay/.env.deploy | cut -d= -f2-)
NURL=$(grep '^FLEET_MEMORY_NATS_URL=' deploy/relay/.env.deploy | cut -d= -f2-)
NU=$(echo "$NURL" | sed -E 's#nats://([^:]+):.*#\1#'); NP=$(echo "$NURL" | sed -E 's#nats://[^:]+:([^@]+)@.*#\1#')
NATS=(nats --server nats://127.0.0.1:4222 --user "$NU" --password "$NP")
psql "$DSN" -tAc 'select count(*) from store;'                 # expect 338 (start point)
curl -s http://127.0.0.1:9000/v1/embeddings -H 'content-type: application/json' \
  -d '{"model":"embed","input":"x"}' | python3 -c "import sys,json;print('embed dim',len(json.load(sys.stdin)['data'][0]['embedding']))"  # 1024
"${NATS[@]}" stream info MEMORY | grep Messages                 # 447 in stream
```

### 1. Rebuild the relay with the fixed code (THE easy-to-miss step)
```bash
cd ~/Projects/appmilla_github/fleet-memory/deploy/relay
docker compose up -d --build          # rebuilds fleet-memory-relay image from current source
docker compose logs --tail 5          # expect "FastStream app started successfully!"
docker image inspect fleet-memory-relay --format 'built={{.Created}}'   # MUST be today, after the fix commits
```

### 2. Replay all 447 from the stream
The durable consumer has already acked through the stream (dropping the 109). To
re-read everything, delete the durable and let the relay recreate it
(`MEMORY_CONSUMER_CONFIG` has no `deliver_policy` → defaults to **DeliverAll** → it
re-reads from seq 1). Replay is **safe**: `ChunkWriter` is idempotent
(`uuid5(episode_id, index)`) so the 338 re-upsert harmlessly and the 109 now embed.
```bash
docker compose stop                                   # quiesce the relay first
"${NATS[@]}" consumer rm MEMORY fleet-memory-relay -f # delete the durable (relay recreates it)
docker compose up -d --force-recreate                 # recreates durable @ DeliverAll → redelivers 447
docker compose logs -f                                # watch Received/Processed (far fewer nacks now)
```
> If for any reason the recreated consumer does NOT start from the beginning,
> force it: `"${NATS[@]}" consumer add MEMORY fleet-memory-relay --pull --deliver all --ack explicit --max-deliver 5 --wait 60s` (or set `opt_start_seq`/`DeliverPolicy=all` in `MEMORY_CONSUMER_CONFIG`). Confirm the relay's `@broker.subscriber` adopts it.

### 3. Verify (the invariant: published == stored-episodes + DLQ, no silent gap)
```bash
# all 447 episodes represented (store grain is per-CHUNK now; count DISTINCT episodes)
psql "$DSN" -tAc "select count(distinct value->>'episode_id') from store where prefix like 'fleet_memory.guardkit%';"   # expect 447
psql "$DSN" -tAc 'select count(*) from store_vectors;'        # now >> 447 (multi-chunk episodes -> many chunks)
psql "$DSN" -tAc 'select distinct vector_dims(embedding) from store_vectors;'   # 1024 only
# DLQ now VISIBLE if anything still fails (e.g. a single chunk > 8192 tok) — investigate, don't ignore
"${NATS[@]}" stream subjects MEMORY 'memory.dlq.>'
docker compose logs --since 15m | grep -iE "dlq|max_deliver_exhausted|PoisonEpisode|ERROR"
```
Expected: **447 distinct episodes** stored, `store_vectors` ≫ 447 (chunks), dim 1024,
DLQ empty (or a small, *named* set you can explain — not a silent gap).

### 4. Close TASK-HARV-007
Once 447 verified, tick AC-007-3..6 (rows landed, embeddings written, no DLQ poison,
idempotent re-run) and `/task-complete TASK-HARV-007` in guardkit. AC-007-2 (publish
as user `guardkit`) already passed: `python -m guardkit.cli.main memory harvest --env-file /path/nats-infrastructure/.env`.

## Then — the FEAT-MEM chain
FEAT-MEM-07 re-index → **FEAT-MEM-05 parity eval vs the Graphiti baseline** →
FEAT-MEM-08 cutover → FEAT-MEM-09 Graphiti decommission. **Lock the embedder
(Qwen/1024) before the parity eval** — it drives retrieval quality; evaluate the
store as it will actually run, with the full 447.

## Gotchas / hard-won facts

- **The relay rebuild (step 1) is the trap.** The fixes are committed but the
  running container is the 2026-06-25 image. Skip the rebuild and the replay
  reproduces the exact 338/447 drop.
- **Replay is idempotent** (`uuid5(episode_id, index)`), so re-reading the 338 is
  harmless — no purge needed, no dup risk.
- **store grain is per-chunk.** Post-recovery `store_vectors` ≫ 447; verify by
  `distinct episode_id`, not row count. (`distinct prefix` = 1 — prefix is the
  namespace, not the episode.)
- **nomic-embed has a HARD 2048 limit** (n_ctx_train=2048; llama.cpp clamps
  `--ctx-size` to it). It was left at 8192/effective-2048 — bumping its ctx is
  ineffective + misleading. graphiti-mcp + forge embed against nomic/768; their
  content must stay ≤2048 tokens or they hit the same cliff (separate concern).
  Qwen embed (n_ctx_train=32768) is genuinely fixable; the two are NOT symmetric.
- **Separate pre-existing issue, NOT part of this:** `finproxy-api` hammers
  `granite-vision-4-1-4b` (exclusive `lpa` matrix set) in a retry loop, conflicting
  with the `all` family (qwen-graphiti / coach-ft-v3 / embed) that forge + graphiti
  keep hot → eviction thrash + connection-reset spam (started ~15:47, independent of
  the embed work). Operator decision (matrix-set capacity vs client retry loop);
  flagged, not fixed.
- Box runs the broker, relay, AND the `:9000` llama-swap the relay embeds against;
  surgical changes only (never the full single-spark bring-up — it deletes 38 model
  names and breaks graphiti/forge/coach/tutor/granite + the relay).

## References
- Fixes: `fleet-memory/tasks/completed/TASK-FIX-{EMBEDCTX01,RELAYBATCH01,RELAYDROP01}-*.md`
- Relay: `src/fleet_memory/relay/{handler.py,service.py}`, `src/fleet_memory/embed.py`
- Prior handoff: `docs/handoffs/HANDOFF-2026-06-25-qwen-embed-switch-and-harvest.md`
- Runbook: `deploy/relay/RUNBOOK-qwen-embed-switch.md`
- guardkit: `TASK-HARV-007` (annotated partial), harvest = `python -m guardkit.cli.main memory harvest`
- Agent memory: `qwen-embed-switch-1024`, `feat-harv-p4-harvest-publisher`
