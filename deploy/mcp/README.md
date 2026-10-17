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

Run the first line from anywhere inside this checkout; it is the only thing here
that depends on where you cloned the repository.

```bash
FLEET_MEMORY_REPO=$(git rev-parse --show-toplevel)
cd ~/.config/fleet-secrets && \
  ~/.local/bin/sops exec-env fleet-memory-pg/relay-env-deploy.enc.env \
  "docker compose -f $FLEET_MEMORY_REPO/deploy/mcp/docker-compose.yml up -d --build"
```

No plaintext env file exists or may be created; `:?` interpolation makes a
bare `up -d` fail loudly. The service reuses the relay's sops env (same
store, same embedder; MCP writes go direct to Postgres — no NATS credential).

## Client registration

Registered once at user scope so every Claude Code session on the box gets it:

```bash
claude mcp add --transport http --scope user fleet_memory http://127.0.0.1:8005/mcp/
```

## Which host names the service accepts

`FLEET_MEMORY_MCP_ALLOWED_HOSTS` is a comma-separated list of the names clients
put in the URL, for example `memory:8005,host.docker.internal:8005,example-host:31822`.
When it is set, the service refuses any other `Host` header with 421 and a
browser `Origin` from another site with 403. `localhost`, `127.0.0.1`, `::1`
and the address the request arrived on are always accepted, and only the name
is compared (the port in an entry is ignored).

List every name a client really uses. specialist-agent and guardkit both
default to `http://host.docker.internal:8005/mcp`, so `host.docker.internal:8005`
must be on the list unless every such client overrides that URL.

Left empty (the default, and this compose file's setting), no host check is
made, as before. The registration below uses `127.0.0.1`, which needs no entry.

## Doors for build sandboxes

A build sandbox never uses the main port. It reaches a narrow door: a second
listener in the same process, over the same store, offering only
`memory_search`, `memory_search_items`, `memory_write_payload` (build outcomes
that replace nothing, never on the factory's own shelves) and
`memory://projects`.

There are two ways to run it. Use one or the other; setting both stops the
service at start.

- **One door for every project** (the original form):
  `FLEET_MEMORY_MCP_SANDBOX_PORT=8006`. It serves any project.
- **One door per sandbox** (17 October 2026):
  `FLEET_MEMORY_MCP_SANDBOX_DOORS=8006:proj_a|proj_b,8007:proj_c`. Each
  comma-separated entry is a port and the projects that door serves,
  separated by `|`. On top of the narrow door's rules, each door:
  - refuses a search (either tool) whose `project` is not on its list, or is
    missing or empty;
  - refuses a write whose payload's `project` is not on its list;
  - lists only its own projects in `memory://projects`.

  A refusal is a plain client error, "this sandbox's memory door does not
  serve that project", which names no project. The service will not start if
  the value is malformed: a missing port or project, a port outside 1-65535,
  the main port, a port or a project listed twice (a project belongs to one
  door only), or a project name that is not lower-case letters, digits and
  `_`.

Give each sandbox its own door and keep a project on one door only. To move a
project to a new sandbox, take it off its old door's list first, then add the
new door with it.

### Running several door ports

All doors run in this one process, so a deployment changes in three places
when it adds a door:

1. **The setting**: add the entry to `FLEET_MEMORY_MCP_SANDBOX_DOORS`.
2. **Publishing**: each door's container port must be reachable from its own
   sandbox only. With host networking (this compose file) each port is
   already on the host. With a bridge network, publish each one, for example
   `"<gateway-address>:<published-port>:8007"`, next to the existing
   `...:8006` line.
3. **The guards**: admit each published port from the sandboxes' machine
   only, as for the first door. If several sandboxes run on one machine they
   arrive from the same address, so each sandbox's own network rules must
   allow only its own door port; the door's project list is the second line
   of defence, not the only one.

The host-name check (`FLEET_MEMORY_MCP_ALLOWED_HOSTS`) compares names only, so
the gateway address listed once covers every door port. If the container has
a health probe that asks each port, add the new port to it.

## Verify

- `docker logs fleet-memory-mcp` → `starting http transport on 0.0.0.0:8005`,
  and NO `MEMORY DEGRADED` line (that line means the store is unreachable and
  the service is serving structured errors instead of memory — fix the store).
- From a Claude Code session: `mcp__fleet_memory__memory_search` with
  `{"project": "guardkit", "query": "anything"}` returns a context block.
