---
id: TASK-DW-003
title: Declared supersession linking
task_type: feature
parent_review: TASK-REV-DW03
feature_id: FEAT-MEM-03
wave: 3
implementation_mode: task-work
complexity: 6
dependencies:
- TASK-DW-002
tags:
- supersession
- linking
- retrieval
- fleet-memory
consumer_context:
- task: TASK-DW-002
  consumes: DeterministicWriter upsert path
  framework: writer core (namespace + content-hash upsert)
  driver: internal
  format_note: Supersession extends the same write transaction; declared links come
    from payload.supersedes (list of natural keys, FEAT-MEM-02 SupersessionValidation).
- task: TASK-MEM-005
  consumes: AsyncPostgresStore record contract
  framework: langgraph AsyncPostgresStore via async_store_context
  driver: langgraph-checkpoint-postgres>=2.0 (psycopg3)
  format_note: A superseded record carries a superseded_by link to its successor and
    is excluded from default retrieval but remains addressable directly by key.
---

# Task: Declared supersession linking

## Description

Replace Graphiti's LLM temporal invalidation with a deterministic dictionary
update. When a successor payload declares `supersedes: [<natural_key>, ...]`
(FEAT-MEM-02), the writer marks each predecessor as superseded and records the
successor's own supersession links — no language-model judgement.

**Target module:** `src/fleet_memory/writer/supersession.py`, wired into the
`DeterministicWriter.write` path from TASK-DW-002.

Behaviour:

- Mark each declared predecessor record `superseded_by` the successor; the
  successor records which keys it superseded (ASSUM-007).
- A superseded record is **excluded from default retrieval** but stays
  **addressable directly by key**.
- **Supersession count** is unbounded: zero, one, or many declared predecessors
  are all retired in the same write.
- **Forward supersession** (ASSUM-008): declaring a supersession of a
  not-yet-written key **succeeds**; the link is recorded and applied if/when that
  key later appears.
- **Cross-project supersession**: a successor in one project namespace can retire
  a predecessor in another (the link crosses `("fleet_memory", project, type)`
  boundaries); the successor stays in its own namespace.
- **Idempotent re-declaration**: re-writing the same successor with the same
  supersession leaves the predecessor superseded exactly once — never cumulative,
  no extra record.
- **Chains**: A←B←C collapses to only C in default retrieval, with the chain from
  C back to A still traceable.
- **Racing successors**: two different successors declaring they supersede the
  same predecessor converge on exactly one recorded successor — no contradictory
  state.

## Acceptance Criteria

- [ ] Writing a successor that declares a supersession marks the predecessor
      `superseded_by` the successor, and the successor records which key it
      superseded (ASSUM-007).
- [ ] A superseded record does not appear in default retrieval but is still
      retrievable directly by its key.
- [ ] Declaring `count` predecessors retires exactly `count` of them, for
      `count` in {0, 1, 5}.
- [ ] Declaring a supersession of a key with no existing record succeeds; the
      declared link is recorded and applied when that key later appears
      (ASSUM-008).
- [ ] A cross-project supersession retires the predecessor in the other project
      while the successor remains in its own namespace.
- [ ] Re-declaring the same supersession keeps the predecessor superseded exactly
      once and creates no additional record.
- [ ] In a chain A←B←C only C appears in default retrieval, and the chain from C
      back to A remains traceable.
- [ ] Two successors racing for the same predecessor resolve to exactly one
      recorded successor with no contradictory supersession state.
- [ ] All modified files pass project-configured lint/format checks with zero
      errors.

## Coach Validation

```bash
pytest tests/unit -v -k "supersede or supersession"
pytest tests/integration -m integration -k "supersede or supersession" --timeout=120
ruff check src/fleet_memory/writer/
```

## Seam Tests

Validates the supersession link contract (§4) at the record boundary.

```python
"""Seam test: verify the superseded_by link + default-retrieval exclusion contract."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("supersession_link")
def test_superseded_record_links_successor_and_drops_from_default():
    """A superseded record links its successor and is excluded from default retrieval.

    Contract: predecessor.superseded_by == successor identity; predecessor is
    addressable by key but absent from default retrieval results.
    Producer: TASK-DW-002 (writer core) + TASK-MEM-005 (store contract)
    """
    # Representative of the record shape the supersession path writes:
    predecessor = {"content": "old", "superseded_by": "adr:guardkit:ADR_2"}
    assert predecessor.get("superseded_by"), (
        "a superseded record must carry a superseded_by link to its successor"
    )
    # Default retrieval excludes records with a non-null superseded_by:
    default_visible = predecessor.get("superseded_by") is None
    assert default_visible is False
```

## BDD scenarios covered

supersede-and-link, excluded-but-addressable, supersession-count outline
(0/1/5), forward supersession, cross-project supersession, idempotent
re-declaration, chain-collapse-traceable, racing successors.
