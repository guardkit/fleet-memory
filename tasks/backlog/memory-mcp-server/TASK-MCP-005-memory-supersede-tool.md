---
id: TASK-MCP-005
title: memory_supersede tool for declared supersession
status: in_review
created: 2026-06-13 16:30:00+00:00
updated: 2026-06-13 16:30:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-MEM06
feature_id: FEAT-MEM-06
wave: 3
implementation_mode: task-work
complexity: 5
estimated_minutes: 70
dependencies:
- TASK-MCP-002
tags:
- mcp
- supersession
- declared
consumer_context:
- task: TASK-MCP-001
  consumes: ServerContext
  framework: FastMCP (stdio server)
  driver: fastmcp
  format_note: Tool reads the store from the wired ServerContext
- task: TASK-MCP-002
  consumes: ToolErrorEnvelope
  framework: FastMCP tool handler
  driver: fleet_memory.mcp.degradation
  format_note: Tool body wrapped by tool_safe; supersession raises propagate to structured
    tool-error results
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 3
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-06
  base_branch: main
  started_at: '2026-06-13T20:19:44.939204'
  last_updated: '2026-06-13T20:51:52.383835'
  turns:
  - turn: 1
    decision: feedback
    feedback: "- Deterministic honesty record (claim_audit_unmodified, severity=should_fix):\
      \ Player claim: Player claimed file .claude/task-plans/TASK-MCP-003-implementation-plan.md.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n- Deterministic honesty record (claim_audit_unmodified,\
      \ severity=should_fix): Player claim: Player claimed file .claude/task-plans/TASK-MCP-004-implementation-plan.md.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n- Deterministic honesty record (claim_audit_unmodified,\
      \ severity=should_fix): Player claim: Player claimed file .claude/task-plans/TASK-MCP-005-implementation-plan.md.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n... and 17 more issues"
    timestamp: '2026-06-13T20:19:44.939204'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
  - turn: 2
    decision: feedback
    feedback: "- Deterministic honesty record (claim_audit_unmodified, severity=should_fix):\
      \ Player claim: Player claimed file .claude/task-plans/TASK-MCP-003-implementation-plan.md.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n- Deterministic honesty record (claim_audit_unmodified,\
      \ severity=should_fix): Player claim: Player claimed file .claude/task-plans/TASK-MCP-004-implementation-plan.md.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n- Deterministic honesty record (claim_audit_unmodified,\
      \ severity=should_fix): Player claim: Player claimed file .claude/task-plans/TASK-MCP-005-implementation-plan.md.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n... and 26 more issues"
    timestamp: '2026-06-13T20:30:46.867497'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
  - turn: 3
    decision: approve
    feedback: null
    timestamp: '2026-06-13T20:38:12.502612'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
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
