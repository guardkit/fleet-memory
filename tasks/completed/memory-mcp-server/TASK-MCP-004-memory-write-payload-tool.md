---
id: TASK-MCP-004
title: memory_write_payload tool through the deterministic writer
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-MEM-06 completed"
pre_sweep_status: in_review
created: 2026-06-13 16:30:00+00:00
updated: 2026-06-13 16:30:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-MEM06
feature_id: FEAT-MEM-06
wave: 3
implementation_mode: task-work
complexity: 6
estimated_minutes: 90
dependencies:
- TASK-MCP-002
tags:
- mcp
- write
- deterministic-writer
- registry
- parity
consumer_context:
- task: TASK-MCP-001
  consumes: ServerContext
  framework: FastMCP (stdio server)
  driver: fastmcp
  format_note: Tool reads the DeterministicWriter from the wired ServerContext
- task: TASK-MCP-002
  consumes: ToolErrorEnvelope
  framework: FastMCP tool handler
  driver: fleet_memory.mcp.degradation
  format_note: Tool body wrapped by tool_safe; writer raises propagate to structured
    tool-error results
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-06
  base_branch: main
  started_at: '2026-06-13T20:19:44.938812'
  last_updated: '2026-06-13T20:30:39.435709'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T20:19:44.938812'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: memory_write_payload tool through the deterministic writer

## Description

Expose `memory_write_payload` as an MCP tool that validates a typed payload at
the boundary, instantiates the registered model via the payload registry, and
dispatches it through the **existing** `DeterministicWriter.write` — the single
write path. There is **no second write path**: the tool must produce records
byte-identical to a relay write of the same payload. On success the tool
acknowledges with the stored memory's derived identity / natural key (ASSUM-006).
Idempotency and content-hash upsert are inherited from the writer — the same
payload written twice yields one record (acknowledged as idempotent).

The tool is the boundary that turns malformed input into clean client errors
(never partial writes).

## Acceptance Criteria

- [ ] `src/fleet_memory/mcp/tools/write.py` exists and registers `memory_write_payload` via the TASK-MCP-001 extension point
- [ ] The tool resolves the payload type through the registry (`get_model_for_type` / `PAYLOAD_REGISTRY`) and instantiates the typed model before writing
- [ ] On success the result acknowledges the stored memory's **derived identity** (natural key `type:project:identifier`)
- [ ] An **unknown** payload type (e.g. `meeting_notes`) is rejected with a "type not recognised" tool-error and **nothing is persisted**
- [ ] A payload whose **identifier contains invalid characters** (e.g. spaces) is rejected with an "identifier is invalid" tool-error and nothing is persisted
- [ ] A payload **missing a required field** (e.g. project) is rejected naming the missing field, nothing persisted
- [ ] An untyped / free-form write (not a registered payload type) is rejected as untyped
- [ ] A **client-supplied stored identity is ignored**; the record is stored under the server-derived key (forged-identity scenario)
- [ ] Writing the **same payload twice** results in a single record; the second write is acknowledged as idempotent
- [ ] When the store raises `TimeoutError` the tool returns "memory store unavailable" and the server stays running; when embeddings are unavailable the write is rejected with a retryable message leaving **no partial record** (ASSUM-009)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_mcp_write.py` — derived-identity ack, unknown type rejected, invalid identifier rejected, missing field rejected, untyped rejected, forged identity ignored (uses a fake/in-memory store or fake writer)
- [ ] `tests/unit/test_mcp_write.py::test_idempotent_double_write`
- [ ] `tests/unit/test_mcp_write.py::test_store_down_degrades` and `::test_embed_down_no_partial_write`
- [ ] `tests/integration/test_mcp_write_parity.py` — `@pytest.mark.integration`: a payload written via the tool is byte-identical in stored form to a relay write of the same payload; covers the concurrent same-key and MCP-vs-relay-race convergence to one record

## BDD Scenarios Covered

- "An MCP client writes a typed ADR and then finds it by search" (write half)
- "The write tool persists a typed payload through the deterministic writer"
- "A payload written through the tool is byte-identical in store form to a relay write"
- "The write tool rejects an unknown payload type"
- "The write tool rejects a payload whose identifier contains invalid characters"
- "The write tool rejects a payload missing a required field"
- "An untyped free-form write is not accepted"
- "A client-supplied stored identity is ignored in favour of the derived key"
- "Writing the same payload twice produces a single memory record"
- "The write tool degrades gracefully when the store is unreachable"
- "A write is handled cleanly when the embedding service is unavailable"
- "Two clients writing the same memory at the same time produce a single record"
- "An MCP write racing a relay write of the same payload yields one record"

## Seam Tests

The following seam test validates the integration contract with the deterministic writer. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify the DeterministicWriter contract consumed by memory_write_payload."""
import inspect

import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("DeterministicWriter")
def test_writer_write_contract():
    """Verify the writer exposes the single write path the tool dispatches to.

    Contract: DeterministicWriter.write(payload) is async and is the only write
    path (parity with relay writes).
    Producer: FEAT-MEM-03 (fleet_memory.writer)
    """
    from fleet_memory.writer.core import DeterministicWriter

    assert hasattr(DeterministicWriter, "write")
    assert inspect.iscoroutinefunction(DeterministicWriter.write)
```

## Implementation Notes

- Writer contract verified in source:
  `DeterministicWriter.write(payload: BasePayload)` ([writer/core.py](src/fleet_memory/writer/core.py))
  — performs registry validation, namespace validation, identity derivation,
  content-hash upsert, and supersession application. Idempotency and
  byte-identical storage are properties of this method; the tool must not
  re-implement any of it.
- Resolve types via [registry.py](src/fleet_memory/payloads/registry.py)
  (`get_model_for_type`, `PAYLOAD_REGISTRY`); identifier/required-field validation
  is enforced by the Pydantic payload models — surface their `ValidationError`
  through the TASK-MCP-002 client-error result.
- Derived identity comes from `record_identity(natural_key)`
  ([writer/identity.py](src/fleet_memory/writer/identity.py)); the natural key is
  `payload.natural_key`. Never trust a client-supplied identity field.
- For the embeddings-down case (ASSUM-009): the writer's embed-on-write must fail
  closed — assert no record is left behind.
