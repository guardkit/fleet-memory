---
complexity: 4
dependencies: []
feature_id: FEAT-MEM-03
id: TASK-DW-001
implementation_mode: task-work
parent_review: TASK-REV-DW03
status: completed
tags:
- identity
- hashing
- determinism
- fleet-memory
task_type: feature
title: Record identity and content-hash helpers
wave: 1
---

# Task: Record identity and content-hash helpers

## Description

Provide the two pure, I/O-free derivations the writer is built on: a stable
**record identity** (UUIDv5 from the payload's natural key) and a **content
hash** over the payload's semantic content. No store, no embed, no LLM — just
deterministic functions over a `BasePayload`.

**Target module:** `src/fleet_memory/writer/identity.py`
(create the `src/fleet_memory/writer/` package with an `__init__.py`).

- `record_identity(natural_key: str) -> uuid.UUID` — `uuid.uuid5(NAMESPACE, natural_key)`
  using a **single fixed application-wide namespace UUID constant** declared in
  this module (ASSUM-001, ASSUM-002). The same natural key must always resolve
  to the same UUID across processes and runs.
- `content_hash(payload: BasePayload) -> str` — a stable hash over the payload's
  **semantic content only**, excluding `version` and any write-time metadata
  (timestamps) so an unchanged re-write hashes identically (ASSUM-003). Derive
  the hashed view from `payload.model_dump()` with `version` (and any
  write-time fields) removed; hash a canonical (sorted-key) serialization.

The natural key shape is `<payload_type>:<project>:<identifier>` as produced by
`BasePayload.natural_key` (FEAT-MEM-02). Do not re-derive it here — consume it.

## Acceptance Criteria

- [ ] `record_identity` returns a UUIDv5; the same natural key yields a
      byte-identical UUID on repeated calls and across separate processes
      (ASSUM-001).
- [ ] The UUID namespace constant is a single module-level constant reused by
      every call — no per-call or per-type namespace (ASSUM-002).
- [ ] Two payloads with the same `payload_type`/`project`/`identifier` resolve
      to the same identity; any differing segment resolves to a different
      identity.
- [ ] `content_hash` is identical for two payloads whose semantic content is
      equal but whose `version` differs (ASSUM-003).
- [ ] `content_hash` differs when any byte of semantic content differs,
      including a single-character change.
- [ ] Both functions are pure: no network, no database, no filesystem, no LLM
      import — verifiable by inspection and by the zero-LLM negative test
      (TASK-DW-004).
- [ ] All modified files pass project-configured lint/format checks with zero
      errors.

## Coach Validation

```bash
pytest tests/unit -v -k "identity or content_hash"
ruff check src/fleet_memory/writer/
```

## Implementation Notes

- Keep this module dependency-light: `uuid`, `hashlib`, `json`, and the
  `BasePayload` type only. It must be importable without touching settings,
  the store, or httpx.
- Canonicalize before hashing (`json.dumps(..., sort_keys=True,
  separators=(",", ":"))`) so dict ordering never changes the hash.