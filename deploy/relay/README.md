# fleet-memory relay deployment (GB10)

Durable FastStream consumer on the NATS `MEMORY` stream that writes memory episodes to
the NAS Postgres+pgvector store (FEAT-MEM-04, post-Graphiti write path v2).

This is the relay deployment artifact the GB10 handoff flagged as missing. It runs the
relay as a managed container (`restart: unless-stopped`) so it survives reboots and crashes
— replacing the ad-hoc `faststream run` process used during bring-up.

## Prerequisites (already live on the GB10)

- `ships-computer-nats` broker running, with the `fleet-memory` NATS user provisioned and
  the `MEMORY` stream created (`memory.episode.>` + `memory.dlq.>`). See `nats-infrastructure`.
- Postgres with pgvector installed, reachable from this host at the address you put in
  `FLEET_MEMORY_PG_DSN`.
- Embed service reachable from this host at the address you put in `FLEET_MEMORY_EMBED_URL`.

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

## The progress marker (liveness fence, ladder ⑦)

A clean ingest is completely silent — the relay logs only failures — so from outside
the container "working" and "dead" look identical. That is how the memory flywheel went
dark for a month without anyone noticing.

The relay therefore writes one small file after every message:

```
/var/lib/fleet-memory/relay-progress.json      (inside the container)
~/.local/state/fleet-memory/relay-progress.json (on the host, via the bind mount)
```

It records when the relay started, when it last wrote something to memory, when it last
received anything at all, and how many of each since start. The liveness fence
(`python -m fleet_memory.fence`, units in `ops/fence/`) reads it from the host.

Three things to know:

- **Any relay code change needs a rebuild + recreate anyway** (the Dockerfile copies
  `src/` into the image), so adding the marker costs no extra deploy step — but the
  marker only starts existing after that rebuild. Until then the fence reports that it
  cannot see the relay, which is the honest answer.
- **It is written by the relay's own user (uid 1000) and world-readable (`-rw-r--r--`),
  on purpose.** Since 16 October 2026 the image runs as an ordinary user, `memory`,
  uid/gid 1000, not as root. With this file's bind mount the relay writes into a host
  folder, so that folder must exist and belong to uid 1000 before the first start (see the
  next point): if Docker has to create a missing bind folder itself, it creates it owned by
  root, whoever runs the command. The mode
  is the part that matters for the fence: the fence runs as your own user, so the relay
  sets `0644` on every write. Left at the `0600` a temporary file is created with, the
  marker could be unreadable to the fence, and it would report BLIND forever — the very
  silence this marker exists to end.
  If you ever see the marker at `-rw-------`, the running relay image predates that fix;
  rebuild it rather than chmod-ing the file, which the next message would overwrite.
- **A state folder or volume written while the relay ran as root needs one ownership
  change.** A new named volume is fine: Docker fills it from the image's
  `/var/lib/fleet-memory`, which the image makes owned by uid 1000. But Docker only does
  that for an empty volume, so a volume (or host folder) that already holds a root-owned
  folder and marker stays root-owned. The relay still starts and its health check still
  passes, because the old marker is there, but it cannot replace the marker: it logs
  `Relay progress marker could not be written (PermissionError)` once, the marker stops
  moving, and the fence eventually reports the relay as silent. Fix it once, with the relay
  stopped, before the first start of the non-root image:
  `docker run --rm --user 0 --entrypoint chown -v <volume>:/var/lib/fleet-memory <new relay image> -R 1000:1000 /var/lib/fleet-memory`
  For this file's bind mount, decide by who owns the folder, not by who you are. With the
  relay stopped:
  `mkdir -p ~/.local/state/fleet-memory && stat -c '%u:%g' ~/.local/state/fleet-memory`
  and, if that does not print `1000:1000` (or anything inside it is owned by someone else:
  `find ~/.local/state/fleet-memory ! -uid 1000`),
  `sudo chown -R 1000:1000 ~/.local/state/fleet-memory`.
  Going back to an older root image needs nothing: root can write to a folder owned by 1000.
- **A failed marker write never costs a message.** The writer swallows its own errors
  and logs one warning per process; ingestion and acking are unaffected.

## Verify (RLY-007 gates)

Publish probe episodes as a publisher-capable identity (e.g. `rich`; the `fleet-memory`
user is a consumer and cannot publish `memory.episode.>`):

- **G1 happy** — a `text` episode → one chunk row in `store` (with `episode_type`) + an
  embedding row in `store_vectors`.
- **G3 poison** — a hyphenated `project_id` → parked on `memory.dlq.<project_id>`, message
  terminated (no redelivery), nothing written to `store`.
- **G4 empty** — a whitespace body → acked with zero chunk rows.
