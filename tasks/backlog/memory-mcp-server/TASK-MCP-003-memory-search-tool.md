---
id: TASK-MCP-003
title: memory_search tool over the retrieval API
status: backlog
created: 2026-06-13T16:30:00Z
updated: 2026-06-13T16:30:00Z
priority: high
task_type: feature
parent_review: TASK-REV-MEM06
feature_id: FEAT-MEM-06
wave: 3
implementation_mode: task-work
complexity: 5
estimated_minutes: 70
dependencies: [TASK-MCP-002]
tags: [mcp, search, retrieval, token-budget]
consumer_context:
  - task: TASK-MCP-001
    consumes: ServerContext
    framework: "FastMCP (stdio server)"
    driver: "fastmcp"
    format_note: "Tool reads store + settings from the wired ServerContext"
  - task: TASK-MCP-002
    consumes: ToolErrorEnvelope
    framework: "FastMCP tool handler"
    driver: "fleet_memory.mcp.degradation"
    format_note: "Tool body is wrapped by tool_safe; raises propagate to structured tool-error results"
  - task: FEAT-MEM-05
    consumes: search
    framework: "fleet_memory.retrieval (search + assemble_context) — MERGED to src/ (commit bb92ed2)"
    driver: "fleet_memory.retrieval"
    format_note: "search(SearchRequest, store) -> list[SearchResult]; assemble_context(results, token_budget) -> AssemblyResult(context_block, coverage_score, ...). Default token_budget=2000 when client omits it (ASSUM-001)."
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: memory_search tool over the retrieval API

## Description

Expose `memory_search` as an MCP tool that wraps the FEAT-MEM-05 retrieval
surface (`fleet_memory.retrieval.search` + `assemble_context`). The tool builds a
`SearchRequest`, runs the filtered vector search, assembles a single
token-budgeted context block, and returns the block plus the coverage score
(ASSUM-002). It excludes superseded memories by default via the
`include_superseded` flag defaulting to `False` (ASSUM-008), and applies a
**default token budget of 2000** when the client omits it (ASSUM-001).

**Dependency status: RESOLVED.** The FEAT-MEM-05 retrieval module is now merged
into `src/fleet_memory/retrieval/` (commit `bb92ed2`), exposing `search`,
`assemble_context`, `SearchRequest`, `SearchResult`, `AssemblyResult`. Code this
tool directly against that surface. Unit tests still inject a fake search callable
via `ServerContext` for fast, infra-free coverage; the live integration test runs
unconditionally under `@pytest.mark.integration` (no `importorskip` gate needed —
the module is present).

## Acceptance Criteria

- [ ] `src/fleet_memory/mcp/tools/search.py` exists and registers `memory_search` against the server via the TASK-MCP-001 extension point
- [ ] The tool accepts `project`, `query`, optional `payload_types`, `domain_tags`, `token_budget`, and `include_superseded`; it constructs a valid `SearchRequest`
- [ ] When `token_budget` is omitted, a default of **2000** is applied and the assembled block does not exceed it
- [ ] The tool returns a single assembled context block plus the coverage score; results are scoped to the requested project and ordered most-relevant first
- [ ] `include_superseded` defaults to `False`; superseded memories are absent from default results
- [ ] A query matching nothing returns an **empty** context block and **not** an error
- [ ] A query containing instruction-like text is used only as an opaque search string (no behavioural change)
- [ ] When the store raises `TimeoutError` the tool returns the "memory store unavailable" tool-error; when embeddings raise `EmbedServiceError` it returns the "search temporarily unavailable" tool-error — in both cases the server stays running (via TASK-MCP-002)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_mcp_search.py` — default-budget application, empty-result-not-error, project scoping, ranking order, exclude-superseded default, opaque-query (uses a fake search callable)
- [ ] `tests/unit/test_mcp_search.py::test_store_down_degrades` and `::test_embed_down_degrades`
- [ ] `tests/integration/test_mcp_search_pipeline.py` — `@pytest.mark.integration`; exercises the real merged `search` + `assemble_context` end-to-end

## BDD Scenarios Covered

- "The search tool returns project memories ranked by relevance"
- "The search tool assembles a context block within an explicit token budget"
- "A search with no token budget applies the default budget"
- "A search that matches no memories returns an empty result"
- "Search excludes superseded memories by default"
- "The search tool degrades gracefully when the store is unreachable"
- "The search tool degrades gracefully when the embedding service is unavailable"
- "A search query containing instruction-like text is treated as an opaque query"

## Seam Tests

The following seam test validates the integration contract with the retrieval producer. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify the retrieval search contract from FEAT-MEM-05."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("search")
def test_retrieval_search_contract():
    """Verify the retrieval surface matches the contract memory_search depends on.

    Contract: search(SearchRequest, store) -> list[SearchResult];
              assemble_context(results, token_budget) -> AssemblyResult
              with .context_block and .coverage_score.
    Producer: FEAT-MEM-05 (fleet_memory.retrieval) — merged to src/ (bb92ed2)
    """
    import fleet_memory.retrieval as retrieval

    assert hasattr(retrieval, "search"), "retrieval must expose search()"
    assert hasattr(retrieval, "assemble_context"), "retrieval must expose assemble_context()"
    assert hasattr(retrieval, "SearchRequest"), "retrieval must expose SearchRequest"

    req = retrieval.SearchRequest(project="guardkit", query="x", token_budget=2000)
    assert req.include_superseded is False, "include_superseded must default to False"
```

## Implementation Notes

- Retrieval contract verified in source:
  `search(request: SearchRequest, store) -> list[SearchResult]` and
  `assemble_context(ranked_results, token_budget) -> AssemblyResult(context_block, coverage_score, contributing_types, tokens_used)`.
- `SearchRequest` fields: `project`, `payload_types=[]`, `domain_tags=[]`,
  `query: str | None = None`, `token_budget: int`, `include_superseded: bool = False`.
- Inject the search callable via `ServerContext` (or a small `SearchPort`) so the
  unit tests can substitute a fake while the live module
  (`fleet_memory.retrieval`, now merged) binds at runtime.
- `search`/`store` raise `TimeoutError` (store down) and `EmbedServiceError`
  (embeddings down) — let them propagate into the TASK-MCP-002 wrapper; do not
  catch-and-stringify here.
