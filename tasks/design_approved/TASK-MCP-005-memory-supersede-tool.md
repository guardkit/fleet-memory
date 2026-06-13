---
complexity: 5
consumer_context:
- consumes: ServerContext
  driver: fastmcp
  format_note: Tool reads the store from the wired ServerContext
  framework: FastMCP (stdio server)
  task: TASK-MCP-001
- consumes: ToolErrorEnvelope
  driver: fleet_memory.mcp.degradation
  format_note: Tool body wrapped by tool_safe; supersession raises propagate to structured
    tool-error results
  framework: FastMCP tool handler
  task: TASK-MCP-002
created: 2026-06-13 16:30:00+00:00
dependencies:
- TASK-MCP-002
estimated_minutes: 70
feature_id: FEAT-MEM-06
id: TASK-MCP-005
implementation_mode: task-work
parent_review: TASK-REV-MEM06
priority: high
status: design_approved
tags:
- mcp
- supersession
- declared
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: memory_supersede tool for declared supersession
updated: 2026-06-13 16:30:00+00:00
wave: 3
---

# Task: memory_supersede tool for declared supersession

## Description

Expose `memory_supersede` as an MCP tool that declares supersession (RD-6:
declared, never inferred) by dispatching to the existing
`apply_supersessions(store, successor_natural_key, predecessor_natural_keys)`.
The tool validates the supersession declaration at the boundary — natural-key
shape (`type:project:identifier`), a non-empty predecessor list, no
self-supersession — then applies the links. Forward supersession is supported:
declaring against a not-yet-written predecessor is accepted and takes effect once
the predecessor is written.

## Acceptance Criteria

- [ ] `src/fleet_memory/mcp/tools/supersede.py` exists and registers `memory_supersede` via the TASK-MCP-001 extension point
- [ ] Declaring that a newer memory supersedes an older one marks the older as `superseded_by` the newer; the older no longer appears in default search results
- [ ] A single-predecessor declaration is accepted and marks that one predecessor
- [ ] An **empty predecessor list** is rejected with "at least one predecessor is required" (ASSUM-005) — not a silent no-op
- [ ] A **malformed predecessor reference** (e.g. `not-a-key`) is rejected with "not a valid memory key" and no supersession is applied
- [ ] A memory **superseding itself** is rejected with "a memory cannot supersede itself" and no supersession is applied
- [ ] **Forward supersession**: declaring supersession of a predecessor that has not been written is accepted and takes effect once it is written
- [ ] When the store raises `TimeoutError` the tool returns "memory store unavailable" and the server stays running (via TASK-MCP-002)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_mcp_supersede.py` — single predecessor accepted, empty list rejected, malformed reference rejected, self-supersede rejected (uses a fake/in-memory store)
- [ ] `tests/unit/test_mcp_supersede.py::test_store_down_degrades`
- [ ] `tests/integration/test_mcp_supersede.py` — `@pytest.mark.integration`: marks a predecessor superseded and confirms it drops out of default search; forward-supersession takes effect after the predecessor is written

## BDD Scenarios Covered

- "The supersede tool marks a predecessor memory as superseded"
- "The supersede tool accepts a single predecessor"
- "The supersede tool rejects an empty predecessor list"
- "The supersede tool rejects a malformed predecessor reference"
- "The supersede tool rejects a memory superseding itself"
- "Superseding a predecessor that does not yet exist is accepted"

## Seam Tests

The following seam test validates the integration contract with the supersession surface. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify the apply_supersessions contract consumed by memory_supersede."""
import inspect

import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("apply_supersessions")
def test_apply_supersessions_contract():
    """Verify the supersession surface matches the contract the tool depends on.

    Contract: apply_supersessions(store, successor_natural_key, predecessor_natural_keys)
    is async; predecessor keys are type:project:identifier natural keys.
    Producer: FEAT-MEM-03 (fleet_memory.writer.supersession)
    """
    from fleet_memory.writer.supersession import apply_supersessions

    assert inspect.iscoroutinefunction(apply_supersessions)
    params = list(inspect.signature(apply_supersessions).parameters)
    assert params[:3] == ["store", "successor_natural_key", "predecessor_natural_keys"]
```

## Implementation Notes

- Supersession contract verified in source:
  `async apply_supersessions(store, successor_natural_key, predecessor_natural_keys)`
  ([writer/supersession.py](src/fleet_memory/writer/supersession.py)) — already
  handles forward supersession, cross-project predecessors, and idempotent
  re-marking. It raises `ValueError` on a natural key that is not
  `type:project:identifier`.
- The **empty-list** and **self-supersede** guards are tool-boundary decisions
  (the underlying function returns early on empty input — ASSUM-005); enforce them
  in the tool before calling, and surface as client errors via TASK-MCP-002.
- Default-exclusion of superseded records from search is inherited from the
  retrieval contract (RD-6); this tool only declares the link.