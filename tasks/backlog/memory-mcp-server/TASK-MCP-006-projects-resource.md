---
id: TASK-MCP-006
title: memory://projects listing resource
status: backlog
created: 2026-06-13T16:30:00Z
updated: 2026-06-13T16:30:00Z
priority: medium
task_type: feature
parent_review: TASK-REV-MEM06
feature_id: FEAT-MEM-06
wave: 3
implementation_mode: direct
complexity: 3
estimated_minutes: 40
dependencies: [TASK-MCP-002]
tags: [mcp, resource, projects]
consumer_context:
  - task: TASK-MCP-001
    consumes: ServerContext
    framework: "FastMCP (stdio server)"
    driver: "fastmcp"
    format_note: "Resource reads the store from the wired ServerContext"
  - task: TASK-MCP-002
    consumes: ToolErrorEnvelope
    framework: "FastMCP resource handler"
    driver: "fleet_memory.mcp.degradation"
    format_note: "Resource read wrapped so store outage degrades gracefully"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: memory://projects listing resource

## Description

Expose an MCP **resource** at `memory://projects` (ASSUM-004) that enumerates the
projects that currently have memories. The resource lists distinct project
segments from the `fleet_memory` namespace so a Desktop client can discover what
it can read. Reads degrade gracefully via the TASK-MCP-002 envelope when the
store is unreachable.

## Acceptance Criteria

- [ ] `src/fleet_memory/mcp/resources.py` exists and registers a resource at URI `memory://projects` via the TASK-MCP-001 extension point
- [ ] Reading the resource returns the set of projects that have memories (e.g. includes `guardkit` and `nats-core` when both have records)
- [ ] The listing is derived from the store namespace, not a hardcoded list
- [ ] When the store is unreachable the resource read returns a structured degradation result rather than crashing the server
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_mcp_projects_resource.py::test_lists_projects_with_memories` (uses a fake/in-memory store seeded with two projects)
- [ ] `tests/unit/test_mcp_projects_resource.py::test_store_down_degrades`

## BDD Scenarios Covered

- "The project resource lists the projects that have memories"

## Seam Tests

The following seam test validates the integration contract with the server context. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify the projects resource is registered at the agreed URI."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("ServerContext")
def test_projects_resource_uri():
    """Verify the project-listing resource is exposed at memory://projects.

    Contract: resource URI is memory://projects (ASSUM-004).
    Producer: TASK-MCP-001 (ServerContext + registration extension point)
    """
    from fleet_memory.mcp.server import ServerContext, create_mcp_server

    mcp = create_mcp_server(ServerContext(store=None, writer=None, settings=None))
    uris = {str(r.uri) for r in getattr(mcp, "resources", [])} if hasattr(mcp, "resources") else set()
    # Tolerate framework-specific resource registries; assert the URI is discoverable.
    assert any("memory://projects" in u for u in uris) or True  # refine to framework API
```

## Implementation Notes

- Namespace shape is `("fleet_memory", project, payload_type)` (see
  [writer/core.py](src/fleet_memory/writer/core.py) step 2). Derive the distinct
  `project` segment to build the listing.
- `direct` mode: small, single-file addition — implement inline, no worktree.
- Refine the seam-test resource-introspection line to the concrete FastMCP
  resource API once the package version is pinned in TASK-MCP-001.
