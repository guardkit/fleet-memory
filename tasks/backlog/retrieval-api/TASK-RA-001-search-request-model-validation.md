---
id: TASK-RA-001
title: SearchRequest model and validation
task_type: declarative
parent_review: TASK-REV-RA05
feature_id: FEAT-MEM-05
wave: 1
implementation_mode: task-work
complexity: 4
dependencies: []
status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-05
  base_branch: main
  started_at: '2026-06-13T16:13:41.483578'
  last_updated: '2026-06-13T16:23:03.484831'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T16:13:41.483578'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: SearchRequest model and validation

## Description

Define the typed `SearchRequest` for the retrieval surface and all its
input-validation rules. This is the single normalized contract every
downstream task (search core, assembly, harness) consumes, so it owns every
rejection path the spec's negative scenarios require — before a vector is ever
embedded.

Signature mirrored by the model fields:
`search(project, payload_types, domain_tags, query, token_budget, include_superseded=False)`.

## Acceptance Criteria

- [ ] A `SearchRequest` Pydantic v2 model exists with fields `project: str`,
      `payload_types: list[str] = []`, `domain_tags: list[str] = []`,
      `query: str | None = None`, `token_budget: int`, `include_superseded: bool = False`.
- [ ] A project filter containing a hyphen is rejected; the error states that
      identifiers must use underscores. (scenario: hyphen project rejected)
- [ ] A payload type not in `PAYLOAD_REGISTRY` (the seven canonical types) is
      rejected; the error names the unknown type. `decision_log` is a valid
      example of an unknown type. (scenario: unknown payload type rejected)
- [ ] A domain tag containing injection/delimiter characters
      (e.g. `concurrency' OR '1'='1`) is rejected; the error states the tag is
      malformed. Tags are an exact-match facet. (scenario: malformed domain tag)
- [ ] A negative `token_budget` is rejected; the error indicates the budget must
      not be negative. `token_budget == 0` is accepted (assembly returns empty).
- [ ] A request with neither a `query` nor any filter (no payload_types, no
      domain_tags) is rejected; the error indicates a query or filter is
      required. (ASSUM-008, low confidence — carried as open assumption)
- [ ] An empty `payload_types` list means "all registered types" (not "none").
- [ ] All modified files pass project-configured lint/format checks with zero errors.

## Coach Validation

```bash
pytest tests/unit/test_search_request.py -x
ruff check src/fleet_memory/retrieval/
```

## Implementation Notes

- Reuse `validate_namespace` / underscore conventions already in `store.py` for
  the project-identifier rule; do not invent a second rule.
- Validate payload types against `PAYLOAD_REGISTRY` keys
  (`src/fleet_memory/payloads/registry.py`) — import the registry, never a
  hardcoded list, so the seven canonical types stay a single source of truth.
- Domain-tag validation is a character-class allowlist (letters, digits,
  underscore, hyphen-in-tag is fine; quotes/operators are not). The constraint
  exists to keep tags an exact-match facet, not to widen the match.
- This is a pure declarative/validation task: no store, no embed, no NATS imports.
