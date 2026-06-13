---
id: TASK-RLY-007
title: Verify relay ack/nak/DLQ contract (D5/D9) against nats-infrastructure
task_type: operator_handoff
parent_review: TASK-REV-RLY04
feature_id: FEAT-MEM-04
wave: 1
implementation_mode: direct
complexity: 2
dependencies: []
tags:
  - operator
  - verification
  - dlq
  - assumptions
  - fleet-memory
---

# Task: Verify relay ack/nak/DLQ contract (D5/D9) against nats-infrastructure

This task is `task_type: operator_handoff` — AutoBuild will not attempt it. The
operator must verify the runtime acceptance criteria below manually against the
sibling `nats-infrastructure` repo (memory-relay scope D5/D9), then record the
confirmed values and mark the task complete via `/task-complete`.

These three assumptions are carried as low-confidence in
`features/relay-integration/relay-integration_assumptions.yaml` and drive the
default values in `Settings` (RLY-006). If the verified values differ, override
them via `FLEET_MEMORY_` env vars — no code change required.

## Required operator follow-up

- **ASSUM-005**: Confirm `max_deliver` is `5` before an episode is parked
  (check the MEMORY-stream consumer config in nats-infrastructure D5).
- **ASSUM-006**: Confirm the dead-letter subject name (exact string in relay
  scope D9) and set `FLEET_MEMORY_DLQ_SUBJECT` to match.
- **ASSUM-013 / empty-body**: Confirm an empty/whitespace-only prose episode
  should produce zero chunks and be **acknowledged** (not parked), and that a
  prose episode interrupted partway through chunking should redeliver to a
  clean idempotent overwrite (no orphaned partial chunks).

## Acceptance Criteria

- [ ] `max_deliver` value confirmed against nats-infrastructure D5 and recorded here
- [ ] Dead-letter subject name confirmed against D9 and set in deployment env
- [ ] Empty-body and partial-chunk handling confirmed to match the implemented behaviour
- [ ] Any divergence from the assumed defaults applied via `FLEET_MEMORY_` env (not code)
