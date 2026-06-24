# Decision: FEAT-MEM-04 relay JetStream durability contract (D5/D9)

**Date:** 2026-06-24
**Status:** SUPERSEDED IN PART — the authoritative write-path design is now
`nats-infrastructure/docs/design/specs/memory-relay/memory-write-path-v2-post-graphiti.md`.
This note's durable-pull-consumer mechanics still hold, but the **subjects/schema below were
provisional**: v2 corrects them to the project-partitioned scheme (`memory.episode.>` /
`memory.dlq.{project_id}`, `project`→`project_id`, `ack_wait` 60 s). Re-sync this doc after the
v2 `/feature-spec`/`/feature-plan` lands.
**Context:** The relay business logic (routing, chunking, idempotency, writer, exception taxonomy) was AutoBuilt and unit-green on 2026-06-13, but the JetStream durability layer was deferred (`TASK-RLY-007`, `operator_handoff` — needs a live broker). Until this contract is wired, `@broker.subscriber("MEMORY")` was a plain **core-NATS** subscription, so `NackMessage`/`RejectMessage`/`max_deliver` were no-ops and there was no stream to consume from. This note records the decisions that close that gap.

## Ownership split

| Concern | Owner | Where |
|---|---|---|
| MEMORY stream provisioning (subjects `memory.>`) | `nats-infrastructure` | `streams/stream-definitions.json` + `streams/provision-streams.sh` |
| Durable consumer config (ack policy, max_deliver, ack_wait) | `fleet-memory` relay | `src/fleet_memory/relay/handler.py` |
| Identity scoping (`MEMORY.>`) | `nats-infrastructure` | account/user config |

The relay **binds** to the stream with `JStream(name="MEMORY", declare=False)` — it never creates the stream. This keeps storage/retention policy with the infra repo and means the relay needs no stream-admin permissions. The stream NAME is `MEMORY` (uppercase, like every other stream); its SUBJECTS are lowercase `memory.>` (matching `pipeline.>`, `agents.>`, …).

## D5 — delivery / consumer contract

- **Stream `MEMORY`**, subjects `["memory.>"]`, `retention: limits`, `storage: file`, `replicas: 1`. A single stream carries both the ingest subject and the DLQ subject; `limits` (not `work`) retention so acked episodes and parked poison both age out by `max_age` rather than being deleted on ack — the durable store of record is Postgres, this stream is a replayable transport buffer.
- **Durable PULL consumer** `fleet-memory-relay` with **filter subject `memory.episode`** (ingest only — it never consumes `memory.dlq`). Pull is FastStream's recommended durable pattern and allows a future second relay instance to share the consumer; push+durable cannot scale.
- `ack_policy = explicit`, `ack_wait = 30s` (one episode = embed + Postgres commit; must finish inside ack_wait or it redelivers), `max_deliver = 5` (`FLEET_MEMORY_MAX_DELIVER`, ASSUM-005).
- **Ack-after-commit:** the handler acks only on clean return from `RelayService.ingest`, i.e. after the durable write commits.
- **Publisher contract:** the harvest publishes `MemoryEpisodeV1` to `memory.episode`.

## D9 — failure routing

- **PoisonEpisodeError** (deterministic; will never succeed) → `RejectMessage` (JetStream `term`, no redelivery) **and** an explicit publish to the DLQ subject `memory.dlq` (`FLEET_MEMORY_DLQ_SUBJECT`, ASSUM-006) with `{episode_id, project, reason, detail, content_format, payload_type}`.
- **TransientIngestError** and any unenumerated exception → `NackMessage` (redeliver up to `max_deliver`); never dead-lettered. *Losing data is worse than redelivering.*
- After `max_deliver` is exhausted for a transient failure, JetStream stops redelivering; the message remains in the stream until `max_age`. JetStream does **not** auto-publish to a DLQ — only deterministic poison is explicitly dead-lettered.
- `memory.dlq` is captured by the same `memory.>` stream and retained for inspection, but the relay consumer's `memory.episode` filter means parked poison is never redelivered to the relay. (A dedicated DLQ consumer/alert can be added later.)

## ASSUM-013 — empty / partial

- Empty/whitespace-only prose episode → **zero chunks, acked** (not parked): nothing to write is success, not poison.
- A prose episode interrupted mid-chunking redelivers to a clean idempotent overwrite (episode_id-derived chunk ids), leaving no orphaned partial chunks.

## Live verification (TASK-RLY-007 — GB10 only)

Run against the live broker (`nats-infrastructure` on the GB10) + NAS Postgres (`whitestocks:5433`):

1. `nats-infrastructure/streams/provision-streams.sh` after adding the `MEMORY` stream (`memory.>`); confirm the stream + the `fleet-memory-relay` consumer (filter `memory.episode`, `max_deliver=5`) exist.
2. Run the relay (`FLEET_MEMORY_PG_DSN`, `FLEET_MEMORY_EMBED_URL`, `FLEET_MEMORY_NATS_URL`, `FLEET_MEMORY_DLQ_SUBJECT`, `FLEET_MEMORY_MAX_DELIVER`).
3. Publish a valid `MemoryEpisodeV1` to `memory.episode` → row lands in NAS Postgres.
4. Publish a poison episode → 5 deliveries then parked on `memory.dlq`; not in Postgres.
5. Publish an empty-prose episode → acked, zero chunks.
6. Confirm the assumed defaults match the provisioned consumer; override divergences via `FLEET_MEMORY_` env (no code change). Then `/task-complete TASK-RLY-007` and reconcile `FEAT-MEM-04.yaml` to completed.
