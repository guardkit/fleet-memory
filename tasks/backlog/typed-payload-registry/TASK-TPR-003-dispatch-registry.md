---
id: TASK-TPR-003
title: Payload dispatch registry and round-trip
task_type: feature
parent_review: TASK-REV-C42F
feature_id: FEAT-MEM-02
wave: 3
implementation_mode: task-work
complexity: 5
dependencies:
- TASK-TPR-002
tags:
- registry
- dispatch
- serialization
- fleet-memory
consumer_context:
- task: TASK-TPR-002
  consumes: payload model classes
  framework: Pydantic v2 (model_validate / model_dump)
  driver: pydantic>=2
  format_note: Registry maps each canonical payload_type name to exactly one model
    class (bijection); round-trip rebuilds via registry[name].model_validate(serialized)
status: in_review
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-02
  base_branch: main
  started_at: '2026-06-13T11:10:47.602282'
  last_updated: '2026-06-13T11:55:04.574674'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-13T11:10:47.602282'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Payload dispatch registry and round-trip

## Description

Build the single `payload_type` → model dispatch registry that both the
deterministic writer (FEAT-MEM-03) and relay consumer (FEAT-MEM-04) route
through. Provide name→model lookup, model→name reverse lookup, and the
serialize→dispatch→rebuild round trip.

**Target module:** `src/fleet_memory/payloads/registry.py`
Add an `UnknownPayloadTypeError` to
[errors.py](../../../src/fleet_memory/errors.py) (names the offending type;
no silent fallback — ASSUM-010).

## Acceptance Criteria

- [ ] `review_report` resolves to the ReviewReport model; all seven declared
      types are registered and dispatchable (ASSUM-004).
- [ ] The registry is a bijection: every name maps to exactly one model and no
      two names map to the same model.
- [ ] A payload reports the type name it dispatches under, and that name
      resolves back to its model.
- [ ] Looking up an unknown type (e.g. `decision_log`) is rejected with an
      error naming the unknown type — no fallback to Document (ASSUM-010).
- [ ] Lookup is case-sensitive: `ADR` is rejected as unknown (ASSUM-010).
- [ ] A payload serialized then rebuilt by dispatching on its `payload_type`
      equals the original, with an unchanged natural key.
- [ ] The natural key is identical across repeated serialization round trips
      (determinism).
- [ ] The same payload serialized by either write surface produces
      byte-for-byte identical serialized form.
- [ ] Re-authoring the same natural key with new content advances `version`
      deterministically; the natural key is unchanged.
- [ ] Unknown extra fields in serialized input are ignored on rebuild
      (ASSUM-009).
- [ ] Two payloads with identical type/project/identifier produce the same
      natural key.
- [ ] All modified files pass project-configured lint/format checks with zero
      errors.

## Coach Validation

```bash
pytest tests/ -v -k "payload or registry"
ruff check src/fleet_memory/payloads/
```

## Seam Tests

The following seam test validates the registry round-trip contract — the
cross-surface boundary both write paths depend on. Implement it to verify the
boundary before integration.

```python
"""Seam test: verify payload round-trip contract via the dispatch registry."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("payload_round_trip")
def test_payload_round_trip_is_deterministic():
    """A payload survives serialize -> dispatch -> rebuild unchanged.

    Contract: registry[payload_type].model_validate(model_dump(payload))
              equals the original; natural_key is byte-stable across repeats.
    Producer: TASK-TPR-002 (model classes) + TASK-TPR-001 (BasePayload)
    """
    from fleet_memory.payloads.models import AdrPayload
    from fleet_memory.payloads.registry import PAYLOAD_REGISTRY

    original = AdrPayload(project="guardkit", identifier="ADR_SP_007", source_ref="x")
    serialized = original.model_dump()
    model = PAYLOAD_REGISTRY[original.payload_type]
    rebuilt = model.model_validate(serialized)

    assert rebuilt == original
    assert rebuilt.natural_key == original.natural_key == "adr:guardkit:ADR_SP_007"
```

## BDD scenarios covered

registry resolves name→model, every-type-dispatchable Outline, round-trip
equality, unknown-type rejection, case-sensitivity, bijection, model→name,
determinism (regression), byte-identical (regression), version advance,
extra-field ignore, shared-natural-key dedup.
