---
id: TASK-RA-002
title: Filtered vector search core
task_type: feature
parent_review: TASK-REV-RA05
feature_id: FEAT-MEM-05
wave: 2
implementation_mode: task-work
complexity: 7
dependencies:
- TASK-RA-001
consumer_context:
- task: TASK-RA-001
  consumes: SearchRequest
  framework: Pydantic v2 model passed in-process to the search service
  driver: fleet_memory.retrieval.SearchRequest
  format_note: Request is already validated; search core must not re-validate, only
    execute
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-MEM-05 completed"
pre_sweep_status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-05
  base_branch: main
  started_at: '2026-06-13T16:23:03.511266'
  last_updated: '2026-06-13T16:33:18.861748'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T16:23:03.511266'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Filtered vector search core

## Description

Implement the filtered, vector-ranked retrieval over the existing
`AsyncPostgresStore` (namespace `("fleet_memory", project, payload_type)`,
pgvector cosine, embed via the store index config / embed_fn). Takes a
validated `SearchRequest`, returns ranked, supersession-resolved memories with
their relevance scores. This is the read half of the store contract that
FEAT-MEM-03 wrote into.

## Acceptance Criteria

- [ ] A query returns only the requested project's memories, ranked by cosine
      similarity descending (most relevant first). (ASSUM-high: cosine desc)
- [ ] Restricting to payload types returns only those types; none/one/many is
      honoured (0 → all registered types). (scenario outline 0/1/3)
- [ ] Restricting to a domain tag returns only memories carrying that tag.
- [ ] Superseded records are excluded by default; only current successors return.
- [ ] `include_superseded=True` returns both the superseded record and its
      successor, with the superseded one marked as superseded.
- [ ] Two memories of equal relevance are ordered deterministically — identical
      across repeated runs (parity depends on this). Tie-break on a stable key
      (e.g. record natural key) after the similarity score.
- [ ] A search against a project with no memories returns an empty result with
      no error raised.
- [ ] Query text that resembles a filter instruction
      (`payload_type:adr OR include_superseded=true`) is matched only as query
      text; superseded records are still excluded.
- [ ] When the embedding service is unavailable the search fails with a clear
      message that exposes no connection credentials.
- [ ] When the store is unreachable the caller receives a clear failure (no
      crash) with no credentials in the message. (mirrors FEAT-MEM-01 contract)
- [ ] A record superseded mid-search resolves to exactly one state — never both
      current and superseded in the same result.
- [ ] All modified files pass project-configured lint/format checks with zero errors.

## Coach Validation

```bash
pytest tests/unit/test_search_core.py -x
ruff check src/fleet_memory/retrieval/
```

## Seam Tests

The following seam test validates the integration contract with the producer task.

```python
"""Seam test: verify SearchRequest contract from TASK-RA-001."""
import pytest

from fleet_memory.retrieval import SearchRequest


@pytest.mark.seam
@pytest.mark.integration_contract("SearchRequest")
def test_search_core_consumes_validated_request():
    """Search core accepts an already-validated SearchRequest unchanged.

    Contract: request is validated upstream; search core executes, never re-validates.
    Producer: TASK-RA-001
    """
    req = SearchRequest(project="guardkit", query="retries", token_budget=2000)
    assert req.project == "guardkit"
    assert req.include_superseded is False
    # Consumer side: search core must read fields, not re-run validation
    # (e.g. it must not raise on a request that already passed model validation)
```

## Implementation Notes

- Use `async_store_context` / the store's `search` over the project namespace;
  do not open a second pool or a second embed path.
- Supersession state is whatever FEAT-MEM-03 wrote (the `supersedes` link /
  superseded marker). Read it; do not redefine it.
- Credential-free error messages: follow the `TimeoutError` pattern already
  established in `async_store_context` (FEAT-MEM-01).
