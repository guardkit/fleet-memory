# RUNBOOK — switch fleet-memory embedder: nomic/768 → Qwen3-Embedding-0.6B/1024

**Status:** planned, NOT yet executed (as of 2026-06-25). Do this **before** the first real
`FEAT-HARV` harvest run, so the first real data is embedded with the final model.
**Decision:** `guardkit/docs/decisions/DECISION-DF-004-two-spark-serving-topology-unified-front-door.md`
§2.1 — standardise on **Qwen3-Embedding-0.6B (1024-dim)**, superseding nomic/768. One dim pinned
end-to-end. (Target dim is **1024** — Qwen3-Embedding-0.6B's native dim; not 1028.)

> **⚠️ Verified corrections (adversarial review 2026-06-25) — read before executing on the live GB10:**
> 1. **Go surgical; NEVER the full bring-up on this box.** `dgx-spark/RUNBOOK-single-spark-bring-up.md`
>    Phase 3.2 overwrites the live llama-swap config and deletes ~38 resolvable model names → breaks
>    `graphiti-mcp`, forge Graphiti, `specialist-agent-architect`, `study-tutor`, the granite vision stack,
>    **and** the relay. Add ONLY the `embed` block (step 0, surgical).
> 2. **Back up 4 surfaces, not just the config** — also `deploy/relay/.env.deploy` (gitignored; only copy)
>    + a note of the original 768/768/`vector(768)` triplet. A config-only rollback re-creates the DLQ failure.
> 3. **Stop the relay FIRST**, then serve/drop/recreate — collapses the DLQ danger window and avoids a
>    `store.setup()` race that could rebuild the table at the stale 768.
> 4. **Strip the `embeddings` alias** from the new `embed` block — live `nomic-embed` already owns it
>    (duplicate-alias collision); the relay only ever calls the literal `embed`.
>
> Full corrected, ordered sequence: `docs/handoffs/HANDOFF-2026-06-25-qwen-embed-switch-and-harvest.md`.

## Why this is load-bearing

The relay embeds on write and stores vectors in `store_vectors.embedding`, a pgvector column whose
**dimension is fixed at column creation** (currently `vector(768)`). The relay also has an
`EmbedDimensionError → poison` guard. So if the **served** embedding dim, the
`FLEET_MEMORY_EMBED_DIMS` setting, and the `store_vectors` column dim don't ALL agree, **every episode
poisons straight to `memory.dlq.*`** (DF-004: "a served-dim ≠ index-dim mismatch silently corrupts
pgvector retrieval"). Get all three to **1024** together.

## Current vs target

| | current | target |
|---|---|---|
| model | `nomic-embed-text-v1.5` (`nomic-embed` on :9000) | **Qwen3-Embedding-0.6B** (served as `embed`) |
| dim | 768 | **1024** |
| `FLEET_MEMORY_EMBED_DIMS` | 768 (default) | 1024 |
| `store_vectors.embedding` | `vector(768)` | `vector(1024)` |
| served at `:9000`? | yes (`nomic-embed`) | **NO — not served yet** (see step 0) |

> Set `export FLEET_MEMORY_PG_DSN=...` first (password in `deploy/nas/.env.deploy`).

## Steps

### 0. Serve Qwen3-Embedding-0.6B on the embed endpoint  ← currently missing
`http://promaxgb10-41b1:9000` (llama-swap) currently serves `nomic-embed` + `qwen-graphiti` but NOT
Qwen3-Embedding-0.6B. The canonical serving spec is the `embed` model block in
`dgx-spark/examples/llama-swap-config.public.yaml` — model name **`embed`** (aliases `qwen3-embedding`
/ `embeddings`), `--embedding --pooling last` (last-token pooling is a Qwen3-Embedding requirement),
1024-dim. Two ways to stand it up:

- **Surgical (keeps the rest of the live fleet):** copy that `embed` block into the live
  `/opt/llama-swap/config/config.yaml` (replace the `nomic-embed` block, or add it alongside), then
  restart llama-swap. Least disruptive to the other models on this box.
- **Full bring-up (clean-box / video path):** run `dgx-spark/RUNBOOK-single-spark-bring-up.md` — its
  Phase 3.2 deploys the public config (which includes `embed`) wholesale. ⚠️ On THIS box
  (`promaxgb10-41b1` is the live host) that **replaces the whole config and removes `nomic-embed`**,
  so the running relay breaks until steps 1–3 below land — back up
  `/opt/llama-swap/config/config.yaml` first and do the relay switch immediately after.

Confirm it's serving at 1024:
```bash
curl -s http://promaxgb10-41b1:9000/v1/models | python3 -c "import sys,json;print([m['id'] for m in json.load(sys.stdin)['data']])"
# expect 'embed' (+ aliases qwen3-embedding / embeddings) to appear
curl -s http://promaxgb10-41b1:9000/v1/embeddings -H 'content-type: application/json' \
  -d '{"model":"embed","input":"dim check"}' \
  | python3 -c "import sys,json;print('dim=',len(json.load(sys.stdin)['data'][0]['embedding']))"
# expect: dim= 1024
```

### 1. Point the relay at the new model
Edit `deploy/relay/.env.deploy` (gitignored, chmod 600):
```
FLEET_MEMORY_EMBED_MODEL=embed              # the served model name (alias: qwen3-embedding)
FLEET_MEMORY_EMBED_DIMS=1024
# FLEET_MEMORY_EMBED_URL stays http://promaxgb10-41b1:9000
```

### 2. Recreate the vector tables at 1024 (store is empty → lossless)
The pgvector column dim is fixed and `store.setup()` only creates tables that don't exist, so the dim
won't change in place. Drop the store + vector tables and let the relay rebuild them at the new dim on
next start. **Safe only while the store has no real data** (true now — verify the count first):
```bash
psql "$FLEET_MEMORY_PG_DSN" -c "select count(*) from store;"   # MUST be 0
psql "$FLEET_MEMORY_PG_DSN" -c "DROP TABLE IF EXISTS store_vectors, vector_migrations, store, store_migrations CASCADE;"
```

### 3. Restart the relay so it re-reads env + rebuilds the schema at 1024
```bash
cd deploy/relay
docker compose up -d --force-recreate     # --force-recreate so the new env_file is picked up
docker compose logs -f                     # expect "FastStream app started successfully!"
psql "$FLEET_MEMORY_PG_DSN" -c "\d store_vectors" | grep embedding   # expect vector(1024)
```

### 4. Verify before trusting it
Publish one probe episode (as `rich` or `guardkit`) and confirm it lands AND is 1024-dim, with nothing
in the DLQ:
```bash
psql "$FLEET_MEMORY_PG_DSN" -c "select format_type(atttypid, atttypmod) from pg_attribute where attrelid='store_vectors'::regclass and attname='embedding';"  # vector(1024)
psql "$FLEET_MEMORY_PG_DSN" -c "select count(*) from store;"                       # >= 1 after a probe
nats stream subjects MEMORY 'memory.dlq.>'                                          # expect: no subjects
```
If episodes land in `memory.dlq.*` with an `EmbedDimensionError`, the served dim ≠ 1024 or
`FLEET_MEMORY_EMBED_DIMS` ≠ the column — re-check steps 0/1. Clean up the probe rows + purge the stream
afterward (see how the relay was bring-up-verified in the GB10 handoff).

### 5. Then run the harvest
`/feature-build FEAT-HARV` → live run (`guardkit memory harvest`). All real data now embeds with
Qwen/1024.

## Rollback
Revert `.env.deploy` to nomic/768, re-drop + rebuild the vector tables at 768, restart. This in-place
reset is only clean while the store is empty; once real data exists, a dim change means a **full
re-embed** (re-run the harvest), not an in-place fix.

## Sequencing note
Lock the embedding model **before** the FEAT-MEM-05 parity eval — that eval compares fleet-memory
retrieval against the Graphiti baseline, and the embedder drives retrieval quality, so you want to be
evaluating the store as it will actually run (Qwen/1024), not a throwaway nomic pass.
