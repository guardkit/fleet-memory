# HANDOFF — Memory write path → GB10 live deploy (2026-06-25)

Resumable handoff. The post-Graphiti memory write path is **code-complete and unit-green** across three
repos; everything below is committed to **local `main`, NOT pushed**. What remains is the live/operator
layer on the GB10. A fresh session can start from Step 0 with no prior chat context.

Authoritative design: `nats-infrastructure/docs/design/specs/memory-relay/memory-write-path-v2-post-graphiti.md`.

## TL;DR

- **P1 publisher** (nats-core), **P2 stream** (nats-infrastructure), **P3 relay** (fleet-memory) are built,
  reconciled to one contract, and unit-green. **Nothing is pushed.**
- **Remaining (operator/live):** push from the Mac → add the `fleet-memory` NATS user → provision streams on
  the live broker → run the relay → RLY-007 live verify → reconcile status → P4 guardkit harvest publisher.
- **Why fleet-memory matters:** it is the Graphiti **replacement** (deterministic Postgres+pgvector, LLM-free
  writes). The "run the harvest on the GB10" goal = P4, which depends on this whole path being live.

## What's done (all on local `main`, UNPUSHED)

| Repo | Commits (ahead of origin) | Content |
|---|---|---|
| **nats-core** | `d1f421e` (Merge FEAT-MEP1) + build checkpoints + `a3bc58f` (P1 brief) — **ahead 11** | P1 publisher: `MemoryEpisodeV1` + `NATSClient.publish_episode()`. Independently verified (843 unit tests). |
| **nats-infrastructure** | `e28af91` (P2 streams) + `fe391d2` (v2 spec + superseded scope) — **ahead 2** | MEMORY stream `[memory.episode.>, memory.dlq.>]`, limits/365d. 257 stream tests pass. |
| **fleet-memory** | `0951620` (P3 relay) + `b4afbde` (MEM-04 doc) — **ahead 2** | Relay aligned to the contract. 472 unit tests pass. |

## The contract (verify against this on the GB10)

- **Publisher** (`nats_core.NATSClient.publish_episode(episode)`): publishes raw `MemoryEpisodeV1` JSON to
  `memory.episode.{project_id}.{episode_type}`, header `Nats-Msg-Id={episode_id}` (JetStream dedupe), rejects
  bodies > 900 KB. **Bypasses `MessageEnvelope`** — raw body.
- **Stream** `MEMORY`: subjects `memory.episode.>` + `memory.dlq.>`, `limits` retention, `max_age 365d`, file, 1 replica.
- **Relay** (`fleet_memory.relay.handler`): durable **PULL** consumer `fleet-memory-relay`, filter
  `memory.episode.>`, `ack_policy=explicit`, `max_deliver=5`, `ack_wait=60s`. Clean return → ack (after Postgres
  commit); `PoisonEpisodeError` → term + publish `memory.dlq.{project_id}`; transient → nak (≤max_deliver).
- **Schema** `MemoryEpisodeV1`: required `episode_id`, `project_id` (accepts legacy `project` via alias),
  `episode_type`, `content_format`, `body`; optional `payload_type`, `source_ref`, `name`, `source`,
  `occurred_at`, `published_at`, `ingest_hints`. (`group_id` dropped; `extra=ignore`.)

---

## Step 0 — push from the Mac (REQUIRED — the GB10 can't pull unpushed work)

On the MacBook:
```bash
for r in nats-core nats-infrastructure fleet-memory; do
  git -C ~/Projects/appmilla_github/$r push origin main
done
```
Then on the GB10, in each repo: `git pull origin main`. (Pushing shares the unit-green code so the GB10 can
deploy + live-verify; the live verification — not the push — is the gate for declaring FEAT-MEM-04 done.)

## Step 1 — add the dedicated `fleet-memory` NATS user

This is the one piece deliberately left for the operator: it gates broker startup and needs a GB10 secret.

**1a.** `nats-infrastructure/config/accounts/accounts.conf.template` — add to the **APPMILLA** `users` array
(mirrors the `forge` user):
```
{
    # fleet-memory relay service identity (FEAT-MEM-04): consumes memory.episode.>
    # (durable pull), publishes poison to memory.dlq.>, plus JetStream API/ACK + reply inboxes.
    user: "fleet-memory"
    password: "${FLEET_MEMORY_NATS_PASSWORD}"
    permissions: {
        publish:   [ "memory.dlq.>", "$JS.>", "_INBOX.>" ]
        subscribe: [ "memory.episode.>", "$JS.>", "_INBOX.>" ]
    }
}
```
**1b.** Keep the password var consistent across **three** files (a test enforces this —
`tests/test_env_example.py::TestConsistencyWithTemplate`):
- `.env.example` → add `FLEET_MEMORY_NATS_PASSWORD=`
- `scripts/docker-entrypoint.sh` → add `FLEET_MEMORY_NATS_PASSWORD` to the required-vars validation loop
- ⚠️ **Same pass: fix the pre-existing `FORGE_NATS_PASSWORD` gap** — it's already missing from `.env.example`/
  entrypoint (those two consistency tests fail on `main` today). Add both vars to keep the set equal.

**1c.** On the GB10, set the secret BEFORE restarting (entrypoint validation will refuse to start the broker
without it):
```bash
# in nats-infrastructure/.env on the GB10 (chmod 600, NOT committed)
echo "FLEET_MEMORY_NATS_PASSWORD=$(openssl rand -base64 24)" >> nats-infrastructure/.env
# then restart the broker container (ships-computer-nats) and confirm it comes up:
curl -s http://127.0.0.1:8222/connz?auth=1 | grep -o 'fleet-memory'   # appears once connected
```

## Step 2 — provision the streams on the live broker

```bash
cd nats-infrastructure
./streams/provision-streams.sh --dry-run   # expect [CREATE]/[UPDATE] for MEMORY
./streams/provision-streams.sh             # live
nats stream info MEMORY                     # subjects: memory.episode.>, memory.dlq.> ; retention limits; max_age 365d
```
The relay binds the stream with `declare=False` and provisions/binds the durable consumer `fleet-memory-relay`
(filter `memory.episode.>`, `max_deliver=5`) on first connect; confirm with `nats consumer info MEMORY fleet-memory-relay`.

## Step 3 — run the relay

⚠️ **There is no relay deployment artifact yet** (only `deploy/nas/` for Postgres). Run it via the FastStream
CLI; a compose service / systemd unit is a follow-up worth creating.

```bash
cd fleet-memory  # with the project installed in a venv (pip install -e .)
export FLEET_MEMORY_PG_DSN="postgresql://fleet_memory:<DB_PW>@whitestocks.tailebf801.ts.net:5433/fleet_memory"
export FLEET_MEMORY_EMBED_URL="http://promaxgb10-41b1:9000"
export FLEET_MEMORY_NATS_URL="nats://fleet-memory:<NATS_PW>@127.0.0.1:4222"
# defaults are fine but confirm vs the provisioned consumer:
export FLEET_MEMORY_DLQ_SUBJECT="memory.dlq"   # handler appends .{project_id}
export FLEET_MEMORY_MAX_DELIVER=5
faststream run fleet_memory.app:app
```
(`FLEET_MEMORY_PG_DSN` + `FLEET_MEMORY_EMBED_URL` are required; the rest have defaults. DB password is in
`deploy/nas/.env.deploy` on the GB10; NATS password is the one from Step 1c.)

## Step 4 — RLY-007 live verification (the three gates)

Publish via the nats-core helper (preferred — exercises the real publisher contract):
```python
# on the GB10, with nats-core installed
import asyncio
from nats_core import NATSClient
from nats_core.events import MemoryEpisodeV1

async def main():
    c = NATSClient(source_id="rly007-probe"); await c.connect("nats://fleet-memory:<NATS_PW>@127.0.0.1:4222")
    # G1 happy: text episode -> row in Postgres
    await c.publish_episode(MemoryEpisodeV1(episode_id="probe-ok-1", project_id="guardkit",
        episode_type="document", content_format="text", body="hello memory relay"))
    # G3 poison: hyphenated project_id -> namespace validation -> parked on memory.dlq.bad-proj
    await c.publish_episode(MemoryEpisodeV1(episode_id="probe-poison-1", project_id="bad-proj",
        episode_type="document", content_format="text", body="should be parked"))
    # G4 empty: empty prose -> ack, zero chunks
    await c.publish_episode(MemoryEpisodeV1(episode_id="probe-empty-1", project_id="guardkit",
        episode_type="document", content_format="text", body="   "))
    await c.close()
asyncio.run(main())
```
Checks:
- **G1** → `psql "$FLEET_MEMORY_PG_DSN" -c "select count(*) from store where key like '%probe-ok-1%';"` returns ≥1.
- **G3** → `nats stream view MEMORY --subject 'memory.dlq.bad-proj'` shows the parked poison; `probe-poison-1`
  NOT in Postgres. (Confirm it took `max_deliver` attempts in the relay logs.)
- **G4** → `probe-empty-1` acked, zero chunk rows written.

Record the confirmed `max_deliver` and DLQ subject; override via `FLEET_MEMORY_*` env if the provisioned
consumer differs (no code change).

## Step 5 — reconcile status, then push

```bash
cd fleet-memory
# /task-complete TASK-RLY-007   (mark the operator task done)
# move tasks/design_approved/TASK-RLY-00{1..6} -> tasks/completed/ ; set .guardkit/features/FEAT-MEM-04.yaml status: completed
git push origin main   # (and nats-infrastructure if Step 1 changed it)
```

## Step 6 — P4: guardkit harvest publisher (the original goal)

Wire guardkit's harvest to publish via `nats_core` `publish_episode()` (`project_id="guardkit"`,
`episode_type` per source: `adr` / `feature_outcome` / `review_report` / `document`). This is what
"run the harvest on the GB10" needs. See `nats-core/docs/design/specs/memory-publisher/P1-memory-publisher-feature-brief.md`
and `NATSClient.publish_episode`. Plan it with `/feature-plan` in the **guardkit** repo.

After harvest publishes, run **FEAT-MEM-07 re-index** into the live NAS Postgres, then the probe-set parity
eval vs the Graphiti baseline (FEAT-MEM-05 harness) → go/no-go → FEAT-MEM-08 cutover → FEAT-MEM-09 decommission.

## Gotchas

- **Nothing is pushed** — Step 0 first, or the GB10 has none of this.
- **Entrypoint validation gates broker startup** — set `FLEET_MEMORY_NATS_PASSWORD` in the GB10 `.env` before
  restarting, or the broker won't come up.
- **Pre-existing `FORGE_NATS_PASSWORD` env-consistency failure** lives in the same files (Step 1b) — fix it in
  the same pass so the consistency tests go green.
- **No relay deployment artifact** — `faststream run` only; a compose/systemd unit is a follow-up.
- **`ack_wait=60s`** assumes embed + Postgres commit finishes in time; if the embed service is slow, raise it
  (env, no code change).
- **AutoBuild false-green pattern** (see `docs/retros/FEAT-MEM-04-relay-integration-retro.md`): always run the
  full unit suite in the real venv before trusting a green build.
- **Synology/Tailscale** (from `docs/runbooks/RUNBOOK-nas-postgres-deploy.md`): DSM upgrades can wipe
  `/etc/sudoers.d/`; disable Tailscale key expiry for `whitestocks`.

## References

- `nats-infrastructure/docs/design/specs/memory-relay/memory-write-path-v2-post-graphiti.md` — authoritative design.
- `nats-core/docs/design/specs/memory-publisher/P1-memory-publisher-feature-brief.md` — P1 publisher.
- `fleet-memory/docs/decisions/MEM-04-relay-jetstream-contract.md` — relay consumer contract.
- `fleet-memory/docs/runbooks/RUNBOOK-nas-postgres-deploy.md` — NAS Postgres provisioning (already live on `whitestocks:5433`).
- `forge/docs/reviews/forge-fleet-state-review-2026-06-24.md` — migration framing (fleet-memory replaces Graphiti).
