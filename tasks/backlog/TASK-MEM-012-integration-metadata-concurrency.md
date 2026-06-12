---
id: TASK-MEM-012
title: "Integration tests: metadata filters and concurrency"
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 7
implementation_mode: task-work
complexity: 5
estimated_minutes: 60
dependencies: [TASK-MEM-010]
tags: [integration-tests, metadata-filter, concurrency, mvcc]
consumer_context:
  - task: TASK-MEM-004
    consumes: EPHEMERAL_PG_DSN
    framework: "pytest session fixture (ephemeral_pg) — seam owned by TASK-MEM-010"
    driver: "docker compose + psycopg3"
    format_note: "Inherits the fixture contract proven by TASK-MEM-010's seam test; same conftest, no new seam stub required"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Integration tests — metadata filters and concurrency

## Description

Marker-gated integration tests for filtered semantic search and concurrent-access
semantics: project-scoped metadata filtering with preserved ranking, concurrent
same-key writes converging on one complete winner, and reads never observing a
partial write (Postgres MVCC). Closes the integration tier with a full-suite green
run and a hermeticity grep.

## Acceptance Criteria

- [ ] Metadata filter: memories from `project_a` and `project_b`, both relevant to the query; `asearch` filtered to `project_a` returns only `project_a` memories, still ranked by relevance with scores present
- [ ] Concurrent same-key writes (ASSUM-003): `asyncio.gather` of two `aput` calls with different content to one key — afterwards `aget` returns exactly one of the two versions in full; never a blend or partial
- [ ] Read-during-write (ASSUM-013): a reader polling `asearch`/`aget` while a writer rewrites the same key only ever observes the complete old or complete new version
- [ ] Full integration tier green: `python -m pytest tests/integration/ -m integration -v --timeout=120` passes (Tasks 010 + 011 + 012 files together)
- [ ] Hermeticity grep: `grep -riE "synology|nas_host|100\.64\." tests/integration/` exits non-zero (no NAS references anywhere in the integration tier)
- [ ] Fixture parallel-isolation re-check: the suite passes when run twice concurrently from two shells (distinct compose projects, distinct ports — documented as a manual-or-CI check in the module docstring if not automated)

## Test Requirements

- [ ] Files: `tests/integration/test_metadata_filter.py`, `test_concurrent_writes.py`
- [ ] All `@pytest.mark.integration`

## BDD Scenarios Covered

- "Semantic search can be constrained by metadata filters"
- "Concurrent writes to the same key leave one complete winner"
- "A search during a concurrent write never sees a partial memory"
- "Parallel test runs each get their own isolated ephemeral instance" (re-verified at suite level)

## Implementation Notes

- Filter mechanism: store values carry a `project` field; `asearch(namespace_prefix, query=..., filter={"project": "project_a"})` — confirm the exact filter parameter shape against the pinned langgraph-checkpoint-postgres version
- The read-during-write loop needs a bounded duration (e.g. 50 iterations) to stay deterministic in CI
- Use distinct content lengths for the two concurrent versions so a blend would be detectable by length alone
