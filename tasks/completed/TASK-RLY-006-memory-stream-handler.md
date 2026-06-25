---
complexity: 6
consumer_context:
- consumes: RelayService.ingest
  driver: python
  format_note: Handler awaits service.ingest(episode); clean return => ACK. Handler
    owns ONLY ack/nak/DLQ dispatch, no business logic.
  framework: pure async service
  task: TASK-RLY-005
- consumes: PoisonEpisodeError / TransientIngestError
  driver: stdlib
  format_note: PoisonEpisodeError => RejectMessage to DLQ subject recording reason;
    TransientIngestError (and unenumerated) => NackMessage for redelivery. ACK only
    on clean return.
  framework: typed exceptions
  task: TASK-RLY-002
dependencies:
- TASK-RLY-002
- TASK-RLY-005
feature_id: FEAT-MEM-04
id: TASK-RLY-006
implementation_mode: task-work
parent_review: TASK-REV-RLY04
status: completed
tags:
- handler
- faststream
- durable-consumer
- ack-nak-dlq
- fleet-memory
task_type: feature
title: Thin MEMORY-stream durable consumer - ack/nak/DLQ dispatch and settings
wave: 4
---

# Task: Thin MEMORY-stream durable consumer - ack/nak/DLQ dispatch and settings

## Description

The only NATS-aware module in this feature. A thin `@broker.subscriber` on the
MEMORY stream (durable consumer) that wires `RelayService.ingest` to JetStream
ack semantics, plus the Settings additions for the DLQ contract. Registered on
the module-level singleton broker via import side-effect in `app.py`.

Files: `src/fleet_memory/relay/handler.py`; edits to
`src/fleet_memory/settings.py` and `src/fleet_memory/app.py`.

**Ack contract (ack-after-commit):**
- `await service.ingest(episode)` returns cleanly → **ACK** (write durably
  committed).
- `PoisonEpisodeError` → **reject/terminate** the message and publish it to the
  dead-letter subject with the recorded reason. Consumer keeps processing.
- `TransientIngestError` (and any unenumerated exception) → **nak** for
  redelivery. The episode is redelivered up to `max_deliver`, after which
  JetStream parks it (or the handler routes it to DLQ — confirm via RLY-007).

**Settings additions** (settings-driven per Context B):
- `dlq_subject: str` (default from ASSUM-006 — confirm exact name via RLY-007)
- `max_deliver: int = 5` (ASSUM-005 default)
- `chunk_target_tokens: int = 1000`, `chunk_overlap_ratio: float = 0.15` (OD-1)

Construct `RelayService` in the lifespan (it already opens the store) and expose
it; the handler pulls it from broker context (mirrors how `store` is exposed in
`app.py` today).

## Acceptance Criteria

- [ ] A durable `@broker.subscriber` is registered on the MEMORY stream and wired into `app.py` via import side-effect
- [ ] On clean `ingest` return the message is ACKed; the episode is NOT acked before the write commits
- [ ] `PoisonEpisodeError` routes the episode to the configured dead-letter subject with its reason recorded; the consumer continues with other episodes
- [ ] `TransientIngestError` negatively-acknowledges for redelivery and does NOT dead-letter
- [ ] An episode failing fewer than `max_deliver` times is redelivered, not parked; on reaching the limit it is parked
- [ ] A poison episode at the head of the stream is parked while valid episodes behind it are processed and acked
- [ ] `Settings` exposes `dlq_subject`, `max_deliver`, `chunk_target_tokens`, `chunk_overlap_ratio` with the documented defaults and `FLEET_MEMORY_` prefix
- [ ] Handler contains no chunking/routing/idempotency logic (delegates entirely to `RelayService`)
- [ ] Unit tests use `TestNatsBroker` wrapping the singleton broker with `service.ingest` stubbed to raise each exception type
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Seam Tests

```python
"""Seam test: verify ack-after-commit + nak/DLQ dispatch contract from RLY-005/002."""
import pytest

from faststream.nats import TestNatsBroker


@pytest.mark.seam
@pytest.mark.integration_contract("ack_nak_dlq")
async def test_clean_ingest_acks_and_transient_naks(monkeypatch):
    """Clean return => ACK; TransientIngestError => nak, no DLQ.

    Contract: ACK only on durable commit; transient => redeliver.
    Producer: TASK-RLY-005 (ingest), TASK-RLY-002 (exceptions)
    """
    # Wrap the module-level broker; inject episodes via tb.publish; assert
    # handler.mock and that no DLQ publish occurs for the transient case.
    ...
```

## Coach Validation

```bash
pytest tests/unit/relay/test_handler.py -v
ruff check src/fleet_memory/relay/handler.py src/fleet_memory/settings.py src/fleet_memory/app.py
python -c "from fleet_memory.app import broker, app"
```

## Implementation Notes

- Use FastStream NATS ack control (`AckPolicy` / `RejectMessage` / `NackMessage`
  or the JetStream `msg.nack()/term()` equivalents the installed faststream
  version exposes) — verify the exact API against the installed faststream
  before coding.
- Follow the module-level singleton + lifespan patterns already in `app.py`;
  the handler imports `broker` from `app`, never the reverse.
- Keep DLQ subject and max_deliver as Settings values (no literals in the
  handler) so RLY-007's verified values drop in via env without code change.