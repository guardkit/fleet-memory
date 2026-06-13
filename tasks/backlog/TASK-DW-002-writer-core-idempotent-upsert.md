---
id: TASK-DW-002
title: Deterministic writer core - idempotent content-hash upsert
task_type: feature
parent_review: TASK-REV-DW03
feature_id: FEAT-MEM-03
wave: 2
implementation_mode: task-work
complexity: 7
dependencies:
- TASK-DW-001
tags:
- writer
- idempotency
- upsert
- embed-on-write
- fleet-memory
consumer_context:
- task: TASK-DW-001
  consumes: record_identity / content_hash
  framework: Python pure functions (uuid5, hashlib)
  driver: stdlib
  format_note: Identity is uuid5(NAMESPACE, natural_key); content_hash excludes version
    and write-time metadata so an unchanged re-write hashes identically.
- task: TASK-MEM-005
  consumes: AsyncPostgresStore record contract
  framework: langgraph AsyncPostgresStore via async_store_context (store.aput/aget)
  driver: langgraph-checkpoint-postgres>=2.0 (psycopg3)
  format_note: Namespace tuple is ("fleet_memory", project, payload_type); the stored
    value MUST carry a "content" string field so the index config (fields=["content"])
    embeds it on write. Validate the namespace with validate_namespace before any put.
- task: TASK-TPR-003
  consumes: typed payload registry
  framework: Pydantic v2 BasePayload + PAYLOAD_REGISTRY dispatch
  driver: pydantic>=2
  format_note: Only registered BasePayload subclasses are writable; unregistered input
    is rejected with an error naming the unrecognized type (no free-form writes).
---

# Task: Deterministic writer core - idempotent content-hash upsert

## Description

Build the heart of FEAT-MEM-03: a `DeterministicWriter` that turns one typed
payload (or a batch) into `AsyncPostgresStore` records with **zero language-model
calls**. Identity comes from TASK-DW-001; persistence and embed-on-write go
through the storage substrate's `async_store_context` (FEAT-MEM-01); the input
contract is the typed payload registry (FEAT-MEM-02).

**Target module:** `src/fleet_memory/writer/core.py` (`DeterministicWriter`),
exported from `src/fleet_memory/writer/__init__.py`.

Write algorithm for a single payload:

1. Reject input that is not a registered `BasePayload` subclass — error names the
   unrecognized type (no untyped free-form writes).
2. Build namespace `("fleet_memory", payload.project, payload.payload_type)` and
   `validate_namespace(...)` **before** any store call (a hyphenated project is
   rejected with the underscores-only error; no record created).
3. Compute identity = `record_identity(payload.natural_key)` and
   new hash = `content_hash(payload)`.
4. Read any existing record for that natural key:
   - **No existing record** → write a new record at `version=1`, embedding the
     `content` field on write.
   - **Existing, same content hash** → **no-op**: leave the stored record
     (content, version, timestamps) untouched and do **not** re-embed (ASSUM-004).
   - **Existing, different content hash** → **versioned update**: store the new
     content and advance `version` by exactly one (ASSUM-005); still one record
     for that key.

Batch write (ASSUM-010): accept an iterable of payloads and produce exactly one
record per distinct natural key, applying the per-key upsert rules above
(within-batch duplicate keys collapse).

Failure modes (all leave **no partial record**):
- Embedding service unavailable → the whole write fails with an error naming the
  embedding service (ASSUM-009).
- Embedding has the wrong dimensions → fail with a dimension-mismatch error.
- Database unreachable → fail fast with a diagnostic naming the database target
  (credentials stripped).
- Interrupted after embed but before commit → on retry, no half-written record is
  observable and the retry yields exactly one complete record.

Identity-forgery guard: delimiter/path-shaped text smuggled into an identifier
field is rejected by the FEAT-MEM-02 identifier validators (underscores-only) —
surface that rejection; never let it forge a different identity.

## Acceptance Criteria

- [ ] Writing a typed payload stores a retrievable record in its project
      namespace, fetchable by its key.
- [ ] The same payload written twice resolves to the same stable record identity
      (UUIDv5 from the natural key).
- [ ] Writing identical content twice leaves exactly one record, unchanged, with
      no re-embed on the second write (ASSUM-004).
- [ ] Writing changed content under the same natural key replaces the content and
      advances `version` by one; still one record for that key (ASSUM-005).
- [ ] Byte-identical content creates no new version; a single-character
      difference is treated as new content and advances the version.
- [ ] A written payload's `content` is embedded as part of the write and is
      findable by semantic search.
- [ ] A batch of `N` payloads with distinct natural keys produces exactly `N`
      records; `N=0` produces none (ASSUM-010).
- [ ] A hyphenated project namespace is rejected before any write with the
      underscores-only error; no record is created.
- [ ] Non-registered input is rejected with an error indicating it is not a
      recognized payload type.
- [ ] Embedding-unavailable, dimension-mismatch, and database-unreachable each
      fail the write as a whole with no partial record left behind.
- [ ] No code path constructs a language-model client (enforced by TASK-DW-004).
- [ ] All modified files pass project-configured lint/format checks with zero
      errors.

## Coach Validation

```bash
pytest tests/unit -v -k "writer and not supersede"
pytest tests/integration -m integration -k "writer and not supersede" --timeout=120
ruff check src/fleet_memory/writer/
```

## Seam Tests

Validates the writer→store record contract (§4): the value handed to the store
carries a `content` field so embed-on-write fires, and the namespace is the
3-tuple the store expects. Implement before integration.

```python
"""Seam test: verify the writer→store record/namespace contract."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("writer_store_record")
def test_writer_record_carries_content_and_namespace():
    """The value the writer stores embeds on write and lands in the right namespace.

    Contract: namespace == ("fleet_memory", project, payload_type); the stored
    value contains a non-empty "content" string field (index config fields=["content"]).
    Producer: TASK-DW-001 (identity/hash) + TASK-MEM-005 (store contract)
    """
    from fleet_memory.writer import DeterministicWriter  # noqa: F401

    # Build the namespace + record value the writer would emit for a payload and
    # assert the contract without a live store:
    namespace = ("fleet_memory", "guardkit", "adr")
    value = {"content": "an ADR body"}  # representative of writer output

    assert namespace[0] == "fleet_memory"
    assert len(namespace) == 3
    assert isinstance(value.get("content"), str) and value["content"], (
        "stored value must carry a non-empty 'content' field for embed-on-write"
    )
```

## BDD scenarios covered

write-and-retrieve, deterministic identity, identical-content no-op,
changed-content versioned update, embed-on-write findable, byte-identical
boundary, single-character boundary, batch outline, hyphen-namespace reject,
not-a-payload reject, embed-unavailable, dimension-mismatch, db-unreachable,
interrupted-write atomicity.
