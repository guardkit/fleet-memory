---
id: TASK-RIP-001
title: Reindex package + path-safe corpus walker
status: backlog
created: 2026-06-13 20:30:00+00:00
updated: 2026-06-13 20:30:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-RIP7
feature_id: FEAT-MEM-07
wave: 1
implementation_mode: task-work
complexity: 4
estimated_minutes: 45
dependencies: []
tags:
- reindex
- corpus
- security
- path-traversal
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Reindex package + path-safe corpus walker

## Description

Establish the `fleet_memory.reindex` package and a **path-traversal-safe** corpus
walker that yields candidate documents (resolved path + raw text) rooted at a
configured corpus root. The walker is the foundation every later task builds on;
its one hard security property is that it **never reads outside the corpus root**,
even when an entry name contains `..` segments or a symlink that escapes the root.

Add a `corpus_root` setting (`FLEET_MEMORY_CORPUS_ROOT`) to the existing
pydantic-settings `Settings` class.

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/__init__.py` and `src/fleet_memory/reindex/walker.py` exist
- [ ] `walk_corpus(root: Path) -> Iterator[CorpusDocument]` yields each markdown document under `root` with its resolved path and raw text
- [ ] Every yielded path, after `Path.resolve()`, is contained within the resolved corpus root; entries containing path-traversal segments or symlink escapes are skipped and never read (a crafted path-traversal name cannot cause a read outside the root)
- [ ] A run over an empty corpus root yields zero documents and does not raise
- [ ] `corpus_root` (`FLEET_MEMORY_CORPUS_ROOT`) is added to `Settings` ([settings.py](src/fleet_memory/settings.py)) with the `FLEET_MEMORY_` prefix convention
- [ ] `tests/unit/reindex/test_walker.py` covers: a path-traversal entry is not read; an empty directory yields nothing
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_walker.py::test_path_traversal_entry_not_read` — an entry whose name contains `../` cannot cause a read outside the resolved root
- [ ] `test_walker.py::test_empty_corpus_yields_nothing`
- [ ] Default `pytest tests/ -q` stays green

## BDD Scenarios Covered

- "A path-traversal filename in the corpus cannot make the pipeline read outside the corpus root"
- "A run over an empty corpus publishes nothing and completes cleanly" (walker contribution)

## Implementation Notes

- Resolve both the root and each candidate path and assert `candidate.resolve()`
  is relative to `root.resolve()` (`Path.is_relative_to`) before reading — this is
  the single line that enforces the containment invariant.
- Keep the walker pure I/O: yield a small `CorpusDocument` dataclass/Pydantic value
  (path, text); no parsing or classification here (that is TASK-RIP-003).
- Mirror the `FLEET_MEMORY_` settings idiom already used for embed/PG config.
