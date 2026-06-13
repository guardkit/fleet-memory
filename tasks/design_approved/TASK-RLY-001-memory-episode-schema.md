---
complexity: 3
dependencies: []
feature_id: FEAT-MEM-04
id: TASK-RLY-001
implementation_mode: task-work
parent_review: TASK-REV-RLY04
status: design_approved
tags:
- schema
- pydantic
- relay
- fleet-memory
task_type: declarative
title: MemoryEpisodeV1 envelope schema, ContentFormat enum, and Chunk model
wave: 1
---

# Task: MemoryEpisodeV1 envelope schema, ContentFormat enum, and Chunk model

## Description

Define the inbound envelope and the prose-path value objects that every other
relay task consumes. Three artifacts in `src/fleet_memory/relay/schema.py`:

1. **`ContentFormat`** — a string enum with exactly `JSON = "json"`,
   `MARKDOWN = "markdown"`, `TEXT = "text"` (the only recognized formats —
   anything else is parked, per the negative scenarios).
2. **`MemoryEpisodeV1`** — the Pydantic v2 envelope published by nats-core onto
   the MEMORY stream. Fields (minimum): `episode_id: str`, `project: str`,
   `content_format: str` (raw string, validated at routing time — an
   unrecognized value must be *parkable*, not a Pydantic error), `body: str`,
   `payload_type: str | None`, `source_ref: str | None`. Use
   `ConfigDict(extra="ignore")` for forward compatibility (matches the
   project's schema convention).
3. **`Chunk`** — a frozen value object produced by the chunker and consumed by
   the chunk writer: `index: int`, `text: str`, `source_ref: str | None`,
   `project: str`. No storage logic here — pure data.

This is the producer side of the §4 `MemoryEpisodeV1` and `Chunk` contracts.

## Acceptance Criteria

- [ ] `ContentFormat` enum defines exactly `json`, `markdown`, `text` and nothing else
- [ ] `MemoryEpisodeV1` parses a valid structured-JSON envelope and a valid markdown envelope without error
- [ ] `content_format` is stored as-is (an unrecognized value like `"yaml"` does NOT raise at parse time — it is routed/parked downstream)
- [ ] `MemoryEpisodeV1` uses `ConfigDict(extra="ignore")` so unknown envelope fields are dropped, not rejected
- [ ] `Chunk` is immutable (frozen) and carries `index`, `text`, `source_ref`, `project`
- [ ] Unit tests assert round-trip parse for each `ContentFormat` and the extra-field-ignore behaviour

## Coach Validation

```bash
pytest tests/unit/relay/test_schema.py -v
python -c "from fleet_memory.relay.schema import MemoryEpisodeV1, ContentFormat, Chunk"
```

## Implementation Notes

- Mirror `ConfigDict(extra="ignore")` and `Field` conventions from
  `src/fleet_memory/payloads/base.py`.
- Do NOT validate `content_format` against the enum at parse time — the
  "unrecognized content format is parked" negative scenario requires the value
  to survive into the routing layer where it becomes a poison decision.
- Keep this module free of NATS, store, and writer imports (declarative only).