# fleet-memory resident MCP service (GB10)

The one memory door: an always-on HTTP MCP server on `:8005` exposing
`memory_search` / `memory_write_payload` / `memory_supersede` (+ the
`memory://projects` resource) over the NAS Postgres+pgvector store.

Born in the 2026-08-03 memory reconnection (see
`ai-transition/docs/memory-reconnection-gap-analysis-and-plan-2026-08-03.md`):
the per-repo stdio topology died of config drift (required DSN lived in
per-repo plaintext `.env` files the DF-022 sops cutover shredded), while the
resident-HTTP topology (graphiti-mcp's) survived untouched for three months.

## Deploy (the ONLY supported start path)

```bash
cd ~/.config/fleet-secrets && \
  ~/.local/bin/sops exec-env fleet-memory-pg/relay-env-deploy.enc.env \
  'docker compose -f ~/Projects/appmilla_github/fleet-memory/deploy/mcp/docker-compose.yml up -d --build'
```

No plaintext env file exists or may be created; `:?` interpolation makes a
bare `up -d` fail loudly. The service reuses the relay's sops env (same
store, same embedder; MCP writes go direct to Postgres — no NATS credential).

## Client registration

Registered once at user scope so every Claude Code session on the box gets it:

```bash
claude mcp add --transport http --scope user fleet_memory http://127.0.0.1:8005/mcp/
```

## Verify

- `docker logs fleet-memory-mcp` → `starting http transport on 0.0.0.0:8005`,
  and NO `MEMORY DEGRADED` line (that line means the store is unreachable and
  the service is serving structured errors instead of memory — fix the store).
- From a Claude Code session: `mcp__fleet_memory__memory_search` with
  `{"project": "guardkit", "query": "anything"}` returns a context block.
