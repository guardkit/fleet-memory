---
id: TASK-TPR-001
title: Payload base conventions and validators
task_type: declarative
parent_review: TASK-REV-C42F
feature_id: FEAT-MEM-02
wave: 1
implementation_mode: task-work
complexity: 6
dependencies: []
tags: [pydantic, schema, fleet-memory]
---

# Task: Payload base conventions and validators

## Description

Define the shared `BasePayload` Pydantic v2 model that every typed payload
inherits. This is the contract that makes fleet-memory writes deterministic:
the natural key, declared supersession, domain tags, source reference, and
version stamp are all defined **once** here and reused by all seven concrete
types (TASK-TPR-002) and the dispatch registry (TASK-TPR-003).

**Approach (from review):** Option 1 — single shared base class.

**Target module:** `src/fleet_memory/payloads/base.py`
(new subpackage `src/fleet_memory/payloads/`, add `__init__.py`).
Reuse the existing underscore-only convention and error style from
[errors.py](../../../src/fleet_memory/errors.py) (`NamespaceValidationError`,
`^[a-z0-9_]+$`).

## Shared fields (ASSUM-001/005/006/007)

- `project: str` and `identifier: str` — segments of the natural key; both
  validated underscore-only (no hyphens, no colons).
- `domain_tags: list[str] = []` — optional lowercase_underscore tokens
  (ASSUM-005), default empty.
- `source_ref: str` — required free-form provenance reference (ASSUM-007).
- `version: int = 1` — monotonic integer starting at 1 (ASSUM-006).
- `supersedes: list[str] = []` — declared natural-key-shaped references.
- computed `natural_key` → `"<payload_type>:<project>:<identifier>"`.
- abstract/overridable `payload_type` classvar (set by each subclass).
- `ConfigDict(extra="ignore")` for forward compatibility (ASSUM-009).

## Acceptance Criteria

- [ ] `natural_key` is `<payload_type>:<project>:<identifier>` — exactly three
      colon-separated segments (ASSUM-001).
- [ ] `project` / `identifier` reject hyphens and colons; error states
      "identifiers must use underscores" (ASSUM-002; covers injection text
      like `ADR:SP:007`).
- [ ] An empty `identifier` is rejected with an error indicating the
      identifier is required.
- [ ] `supersedes` accepts only three-segment natural-key-shaped references;
      malformed references (wrong segment count, free text) are rejected with
      an error indicating the reference is not a valid natural key (ASSUM-003).
- [ ] A payload superseding its **own** natural key is rejected with an error
      that a payload cannot supersede itself (ASSUM-011).
- [ ] A cross-project supersession reference is **accepted** (ASSUM-011).
- [ ] Duplicate supersession references are collapsed to one, order-stable.
- [ ] `domain_tags` defaults to empty and is accepted when absent (ASSUM-005).
- [ ] `version` defaults to 1.
- [ ] Unknown extra fields are ignored on construction (`extra="ignore"`).
- [ ] All modified files pass project-configured lint/format checks with zero
      errors.

## Coach Validation

```bash
pytest tests/ -v -k payload
ruff check src/fleet_memory/payloads/
```

## BDD scenarios covered (acceptance source)

From `features/typed-payload-registry/typed-payload-registry.feature`:
natural-key segment scenarios, empty-identifier, hyphen-in-project,
hyphen-in-identifier, injection-text, supersession-shape (Outline),
self-supersession, cross-project supersession, duplicate-collapse,
no-domain-tags, supersession count Outline (0/1/5).
