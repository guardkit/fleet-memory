# fleet-memory relay deployment (GB10)

Durable FastStream consumer on the NATS `MEMORY` stream that writes memory episodes to
the NAS Postgres+pgvector store (FEAT-MEM-04, post-Graphiti write path v2).

This is the relay deployment artifact the GB10 handoff flagged as missing. It runs the
relay as a managed container (`restart: unless-stopped`) so it survives reboots and crashes
— replacing the ad-hoc `faststream run` process used during bring-up.

## Prerequisites (already live on the GB10)

- `ships-computer-nats` broker running, with the `fleet-memory` NATS user provisioned and
  the `MEMORY` stream created (`memory.episode.>` + `memory.dlq.>`). See `nats-infrastructure`.
- NAS Postgres reachable at `whitestocks.tailebf801.ts.net:5433` (pgvector installed).
- Embed service reachable at `http://promaxgb10-41b1:9000`.

## Deploy

```bash
cd deploy/relay
cp .env.deploy.example .env.deploy
$EDITOR .env.deploy          # fill in the DB + NATS passwords (see comments)
chmod 600 .env.deploy
docker compose up -d --build
docker compose logs -f       # expect: "FastStream app started successfully!"
```

The relay binds the existing durable pull consumer `fleet-memory-relay` (filter
`memory.episode.>`, `max_deliver=5`, `ack_wait=60s`); it does not create the stream
(`declare=False`).

## Networking

Uses `network_mode: host` so the container reaches the broker on `127.0.0.1:4222`, the NAS
Postgres over Tailscale, and the embed service by hostname — exactly as the host does.

## Verify (RLY-007 gates)

Publish probe episodes as a publisher-capable identity (e.g. `rich`; the `fleet-memory`
user is a consumer and cannot publish `memory.episode.>`):

- **G1 happy** — a `text` episode → one chunk row in `store` (with `episode_type`) + an
  embedding row in `store_vectors`.
- **G3 poison** — a hyphenated `project_id` → parked on `memory.dlq.<project_id>`, message
  terminated (no redelivery), nothing written to `store`.
- **G4 empty** — a whitespace body → acked with zero chunk rows.
