---
id: TASK-TPR-002
title: Seven concrete payload types
task_type: declarative
parent_review: TASK-REV-C42F
feature_id: FEAT-MEM-02
wave: 2
implementation_mode: task-work
complexity: 4
dependencies:
- TASK-TPR-001
tags:
- pydantic
- schema
- fleet-memory
consumer_context:
- task: TASK-TPR-001
  consumes: BasePayload
  framework: Pydantic v2 (BaseModel subclassing)
  driver: pydantic>=2
  format_note: Each type subclasses BasePayload and sets a canonical underscore `payload_type`
    classvar; shared validators are inherited, not re-declared
status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-02
  base_branch: main
  started_at: '2026-06-13T11:00:35.062050'
  last_updated: '2026-06-13T11:10:47.577135'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T11:00:35.062050'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Seven concrete payload types

## Description

Implement the seven concrete payload models, each subclassing `BasePayload`
(TASK-TPR-001) and declaring its canonical `payload_type`. Type-specific
required fields live here; the shared conventions are inherited.

**Target module:** `src/fleet_memory/payloads/models.py`

The seven registered types are exactly (ASSUM-004):
`adr`, `review_report`, `build_outcome`, `pattern`, `warning`, `seed_module`,
`document`.

- **Document** is the generic catch-all: it must be accepted without requiring
  any type-specific fields.
- **ReviewReport** must require a `verdict` field (drives the
  "missing required field is rejected" scenario).
- The remaining types carry sensible type-specific fields per their domain;
  keep them minimal — this feature is the schema layer, not the writer.

## Acceptance Criteria

- [ ] Each type's `payload_type` is its canonical underscore name (ASSUM-004).
- [ ] An ADR for project `guardkit` / id `ADR_SP_007` yields natural key
      `adr:guardkit:ADR_SP_007`.
- [ ] A generic Document yields `document:<project>:<identifier>` and is
      accepted with no type-specific fields.
- [ ] A ReviewReport built with no `verdict` is rejected; the error names the
      missing field.
- [ ] Every type inherits the underscore-only / supersession / domain-tag /
      source-ref conventions from `BasePayload` (no re-declaration).
- [ ] All modified files pass project-configured lint/format checks with zero
      errors.

## Coach Validation

```bash
pytest tests/ -v -k payload
ruff check src/fleet_memory/payloads/
```

## BDD scenarios covered

ADR natural key, generic-document acceptance, per-type required field
(review report verdict), domain-tags-and-source-ref carry.
