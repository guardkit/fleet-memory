# Feature: Memory MCP Server (FEAT-MEM-06)

A FastMCP server exposing `memory_search`, `memory_write_payload`, and
`memory_supersede` tools plus a `memory://projects` resource over **stdio** for
Claude Desktop — a drop-in replacement for the Graphiti MCP. Writes dispatch
through the one deterministic write path (byte-identical to relay writes); tool
failures surface as structured tool-error results so the server degrades
gracefully (no crash) when Postgres or the embedding service is down.

- **Spec:** [memory-mcp-server.feature](../../../features/memory-mcp-server/memory-mcp-server.feature) (31 scenarios)
- **Plan & diagrams:** [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md)
- **Review:** TASK-REV-MEM06 · **Feature file:** `.guardkit/features/FEAT-MEM-06.yaml`

## Tasks

| ID | Task | Wave | Type | Cplx | Mode |
|---|---|---|---|---|---|
| [TASK-MCP-001](./TASK-MCP-001-scaffold-fastmcp-server.md) | Scaffold FastMCP server, add `fastmcp` dep, wire lifespan | 1 | scaffolding | 5 | task-work |
| [TASK-MCP-002](./TASK-MCP-002-tool-error-degradation-envelope.md) | Shared tool-error + degradation envelope | 2 | feature | 4 | task-work |
| [TASK-MCP-003](./TASK-MCP-003-memory-search-tool.md) | `memory_search` tool over retrieval API | 3 | feature | 5 | task-work |
| [TASK-MCP-004](./TASK-MCP-004-memory-write-payload-tool.md) | `memory_write_payload` through deterministic writer | 3 | feature | 6 | task-work |
| [TASK-MCP-005](./TASK-MCP-005-memory-supersede-tool.md) | `memory_supersede` declared supersession | 3 | feature | 5 | task-work |
| [TASK-MCP-006](./TASK-MCP-006-projects-resource.md) | `memory://projects` listing resource | 3 | feature | 3 | direct |
| [TASK-MCP-007](./TASK-MCP-007-bdd-and-integration-tests.md) | BDD suite + e2e integration tests | 4 | testing | 5 | task-work |

## Execution

```
Wave 1: TASK-MCP-001
Wave 2: TASK-MCP-002
Wave 3: TASK-MCP-003, TASK-MCP-004, TASK-MCP-005, TASK-MCP-006   (parallel)
Wave 4: TASK-MCP-007
```

## ✅ Key dependency — resolved

`memory_search` (TASK-MCP-003) consumes `fleet_memory.retrieval.search` from
**FEAT-MEM-05**, now **merged into `src/`** (commit `bb92ed2`). The read path is
wired end-to-end; unit tests inject a fake search callable via `ServerContext`,
and the live integration test runs under `@pytest.mark.integration`. No blocking
prerequisites remain.

## Next steps

1. Review [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md) — Data Flow diagram
   (all paths wired) and §4 contracts.
2. Build: `/feature-build FEAT-MEM-06` (or `/task-work TASK-MCP-001` to start manually).
