---
complexity: 6
created: 2026-06-13 20:30:00+00:00
dependencies:
- TASK-RIP-003
estimated_minutes: 90
feature_id: FEAT-MEM-07
id: TASK-RIP-004
implementation_mode: task-work
parent_review: TASK-REV-RIP7
priority: high
status: design_approved
tags:
- reindex
- parsing
- payloads
- integration-contract
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: Deterministic typed parsers (seed_module / adr / review_report / build_outcome)
updated: 2026-06-13 20:30:00+00:00
wave: 3
---

# Task: Deterministic typed parsers

## Description

One deterministic parser per document kind, producing the canonical typed payload:

| Document kind | Payload | Required type-specific fields |
|---|---|---|
| seed module | `SeedModulePayload` | `module_path` |
| ADR | `ADRPayload` | `decision`, `status` |
| review report | `ReviewReportPayload` | `verdict` |
| completed-task outcome | `BuildOutcomePayload` | `status`, `duration_seconds` |

Each parser derives the natural-key segments (`project`, `identifier`) and the
required `source_ref` from the document, **normalizing guardkit IDs (hyphens and
colons → underscores) to satisfy `IDENTIFIER_PATTERN` (`^[a-zA-Z0-9_]+$`)** —
e.g. `ADR-SP-007` → `ADR_SP_007`, `FEAT-MEM-07` → `FEAT_MEM_07`. A document
missing a field its payload type requires yields a structured **unparseable**
result with a reason — not a published payload. Parsing makes **no LLM call**.

This task is the **producer** of the §4 Integration Contract `typed_payload`.

## Acceptance Criteria

- [ ] seed module → `seed_module` payload (`module_path`); ADR → `adr` payload carrying `decision` + `status`; review report → `review_report` payload carrying `verdict`; completed-task outcome → `build_outcome` payload (`status`, `duration_seconds`)
- [ ] Each parser sets `project` and `identifier` matching `^[a-zA-Z0-9_]+$` (hyphens/colons in guardkit IDs normalized to underscores) and a required `source_ref` equal to the source path
- [ ] Each document kind maps to exactly one canonical `payload_type` (the Scenario Outline mapping)
- [ ] A document carrying exactly the required fields for its type parses into a payload (just-inside boundary)
- [ ] A document missing a required field (e.g. an ADR with no `status`) produces an unparseable result with a reason and **no** payload
- [ ] A document body containing database commands / prompt-injection text is carried **byte-for-byte** into the payload content, and no command in the content is executed during parsing
- [ ] Parsing performs no language-model call
- [ ] `tests/unit/reindex/test_parsers.py` covers each kind, the missing-required-field case, identifier normalization, and the injection round-trip
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_parsers.py::test_<kind>_parses_to_canonical_payload` (one per kind)
- [ ] `test_parsers.py::test_missing_required_field_is_unparseable_with_reason`
- [ ] `test_parsers.py::test_hyphenated_guardkit_id_normalized_to_underscores`
- [ ] `test_parsers.py::test_injection_body_carried_verbatim`

## BDD Scenarios Covered

- "A seed module document is parsed into a seed-module payload and published"
- "An ADR document is parsed into an ADR payload carrying its decision and status"
- "A review report document is parsed into a review-report payload carrying its verdict"
- "A completed-task outcome document is parsed into a build-outcome payload"
- "Each corpus document kind maps to its canonical payload type" (Scenario Outline)
- "A document carrying exactly the required fields for its type is published"
- "A document missing a field its payload type requires is not published"
- "A document whose body contains injection-shaped text is published verbatim and stays inert" (parse side)

## Implementation Notes

- Construct the concrete payload models from
  [src/fleet_memory/payloads/models.py](src/fleet_memory/payloads/models.py); let `BasePayload`'s
  `__init__` validation raise `IdentifierValidationError` on a bad identifier and
  convert that into an unparseable result rather than letting it escape.
- Treat content strictly as data — never `eval`/`exec`/template-render the body.
  The injection scenario is satisfied by doing nothing clever: store the bytes.
- `duration_seconds` for build outcomes must be an int; if absent/unparseable,
  that is a missing-required-field unparseable result, not a guess.