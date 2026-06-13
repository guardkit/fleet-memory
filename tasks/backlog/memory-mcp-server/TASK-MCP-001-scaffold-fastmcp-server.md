---
id: TASK-MCP-001
title: Scaffold FastMCP server, add fastmcp dependency, wire lifespan
status: backlog
created: 2026-06-13T16:30:00Z
updated: 2026-06-13T16:30:00Z
priority: high
task_type: scaffolding
parent_review: TASK-REV-MEM06
feature_id: FEAT-MEM-06
wave: 1
implementation_mode: task-work
complexity: 5
estimated_minutes: 60
dependencies: []
tags: [mcp, fastmcp, stdio, scaffolding, lifespan]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Scaffold FastMCP server, add fastmcp dependency, wire lifespan

## Description

Establish the `fleet_memory.mcp` package: a FastMCP server served over **stdio**
for Claude Desktop, plus the dependency wiring that the three tools and the
project resource will hang off. This task owns the server skeleton, the shared
`ServerContext`, the lifespan that builds the store / `DeterministicWriter` /
retrieval `search` callable, and the `python -m fleet_memory.mcp` stdio entry
point. No tools are registered here (Wave 3 adds them) — the server must build,
advertise an empty/partial tool set, and **start even when the store is
unreachable** (degradation is reported only when a tool is actually called).

Add `fastmcp` to `pyproject.toml` core dependencies (it is not currently a
dependency). Pin a version consistent with the `fastmcp-python` template
reference adopted for this repo.

## Acceptance Criteria

- [ ] `fastmcp` is added to `[project].dependencies` in `pyproject.toml` with a pinned lower bound; `python -c "import fastmcp"` exits 0
- [ ] `src/fleet_memory/mcp/__init__.py`, `src/fleet_memory/mcp/server.py`, and `src/fleet_memory/mcp/__main__.py` exist
- [ ] `server.py` exposes `ServerContext` (carrying `store`, `writer`, `settings`) and `create_mcp_server(context: ServerContext) -> FastMCP`
- [ ] `server.py` exposes a `register_all(mcp, context)` extension point that is a no-op when no tool modules are present (Wave-3 tasks each add one import + call here)
- [ ] `__main__.py` builds the server from settings and runs it over **stdio** transport (`mcp.run(transport="stdio")` or equivalent); `python -m fleet_memory.mcp --help` (or a dry-run flag) exits 0 without opening a network port
- [ ] The lifespan/startup path constructs `ServerContext` **lazily** so the server process starts and advertises tools even when Postgres is unreachable at launch (no eager connection on import or startup)
- [ ] `tests/unit/test_mcp_server.py::test_server_builds_without_store` passes (build the server with a fake/None store; assert it constructs and lists its advertised tool set)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_mcp_server.py::test_server_builds_without_store` — `create_mcp_server` returns a FastMCP instance with no store connection attempted
- [ ] `tests/unit/test_mcp_server.py::test_stdio_entrypoint_importable` — `python -c "import fleet_memory.mcp.__main__"` exits 0
- [ ] Default `pytest tests/ -q` run stays green (no integration-marked tests added here)

## BDD Scenarios Covered

- "The server communicates over stdio for a Claude Desktop client"
- "The server exposes the memory tools that replace the Graphiti MCP"
- "The server starts even when the store is unreachable at launch"

## Implementation Notes

- Reuse the existing app-wiring helpers in [app.py](src/fleet_memory/app.py) for
  building the store + `DeterministicWriter` (see the FEAT-MEM-04 lifespan fix in
  commit 6390d1e); do not duplicate connection logic.
- `ServerContext` should hold an already-built `DeterministicWriter`
  ([writer/core.py](src/fleet_memory/writer/core.py)) and the `AsyncPostgresStore`.
- Keep startup lazy: build the store inside the lifespan / first-use, not at module
  import — this is what satisfies "starts even when the store is unreachable".
- stdio only — no HTTP/SSE surface (ASSUM-007, out of scope per OD-3).
- Registration extension point: keep `register_all` a thin dispatcher so Wave-3
  tool tasks each contribute one line; the integrator resolves the small merge in
  TASK-MCP-007 if Conductor workspaces run in parallel.
