---
id: TASK-RLY-002
title: Relay exception taxonomy - PoisonEpisodeError vs TransientIngestError
task_type: declarative
parent_review: TASK-REV-RLY04
feature_id: FEAT-MEM-04
wave: 1
implementation_mode: task-work
complexity: 3
dependencies: []
tags:
  - errors
  - relay
  - ack-nak-dlq
  - fleet-memory
---

# Task: Relay exception taxonomy - PoisonEpisodeError vs TransientIngestError

## Description

The single most safety-critical contract in this feature: the typed exceptions
that decide **dead-letter vs redeliver**. A misclassification dead-letters a
recoverable episode (data loss) or retries a poison episode forever (stream
stall). Add to `src/fleet_memory/errors.py` (the existing errors module):

1. **`PoisonEpisodeError`** — a deterministic, non-recoverable failure. The
   episode will never succeed on redelivery, so it must be parked on the DLQ.
   Carries a `reason: str` (recorded on the DLQ) and optional `detail`.
   Raised for: unparseable body, unknown `payload_type`, payload validation
   failure, unrecognized `content_format`, hyphenated/invalid `project`,
   wrong-dimension embedding.
2. **`TransientIngestError`** — a recoverable downstream failure (embedding
   service unavailable, store unreachable, connection drop). Must be
   negatively-acknowledged for redelivery, never dead-lettered.

**Default-to-transient rule:** document (in the module docstring) that any
*unenumerated* exception escaping the service is treated as transient (nak +
redeliver), never as poison. Losing data is worse than redelivering.

This is the producer side of the §4 exception-taxonomy contract; RLY-005 raises
these and RLY-006 maps them to ack/nak/DLQ.

## Acceptance Criteria

- [ ] `PoisonEpisodeError` and `TransientIngestError` subclass the existing fleet-memory error base
- [ ] `PoisonEpisodeError` carries a `reason` string suitable for recording on the dead-letter subject
- [ ] The two classes are distinguishable by type (not by message string)
- [ ] Module docstring states the default-to-transient policy for unenumerated exceptions
- [ ] Unit test asserts the two are not in the same subtree such that a `TransientIngestError` could be caught as poison (or vice versa)

## Coach Validation

```bash
pytest tests/unit/relay/test_errors.py -v
python -c "from fleet_memory.errors import PoisonEpisodeError, TransientIngestError"
```

## Implementation Notes

- Follow the existing error-class style in `src/fleet_memory/errors.py`
  (`NamespaceValidationError`, `EmbedDimensionError`, etc.).
- The existing `EmbedDimensionError` is a *poison* trigger; the existing
  `EmbedTimeoutError`/`EmbedServiceError` are *transient* triggers. Note this
  mapping in the docstring so RLY-005 wires them correctly.
