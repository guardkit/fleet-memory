---
id: TASK-RIP-005
title: Re-index orchestrator + run-report accounting
status: backlog
created: 2026-06-13 20:30:00+00:00
updated: 2026-06-13 20:30:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-RIP7
feature_id: FEAT-MEM-07
wave: 4
implementation_mode: task-work
complexity: 6
estimated_minutes: 90
dependencies:
- TASK-RIP-002
- TASK-RIP-004
tags:
- reindex
- orchestrator
- accounting
- integration-contract
consumer_context:
- task: TASK-RIP-004
  consumes: typed_payload
  framework: "fleet_memory typed payload registry (BasePayload subclasses)"
  driver: "pydantic v2"
  format_note: "project/identifier must match ^[a-zA-Z0-9_]+$ — guardkit hyphenated IDs normalized to underscores; source_ref required"
- task: TASK-RIP-002
  consumes: memory_episode_routing
  framework: "FastStream NatsBroker / RelayService.ingest content_format routing"
  driver: "nats-core MemoryEpisodeV1 publisher"
  format_note: "content_format must be 'json' and payload_type a registered type so the relay routes to the DeterministicWriter, not the prose chunker"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Re-index orchestrator + run-report accounting

## Description

The pure orchestrator: walk the corpus → classify → parse → publish each
recognized document, producing a `RunReport` that **accounts for every walked
document** as published / unparseable / unrecognized. One bad document never
aborts the run. An empty corpus publishes nothing and completes cleanly. The
no-silent-loss invariant is the spine of this task: every document the walker
yields appears in the report under exactly one disposition.

This task is a **consumer** of the §4 contracts `typed_payload` (from TASK-RIP-004)
and `memory_episode_routing` (from TASK-RIP-002).

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/pipeline.py` exposes `reindex_corpus(...)` that walks, classifies, parses, and publishes, returning a `RunReport`
- [ ] Every recognized document is published as a typed episode declaring the `payload_type` matching its document kind
- [ ] The `RunReport` accounts for every walked document: a published count plus the unparseable list and the unrecognized list — no document is silently dropped
- [ ] A single unparseable document does not abort the run: every valid document is still published and the bad one is reported
- [ ] A run over an empty corpus publishes nothing and completes successfully
- [ ] A full-corpus run publishes a typed episode for every recognized document
- [ ] No language-model / cloud call occurs during the whole run
- [ ] `tests/unit/reindex/test_pipeline.py` (with a fake publisher) covers: full corpus, one-bad-doc-does-not-abort, empty corpus, accounting totals sum to documents walked
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_pipeline.py::test_full_corpus_publishes_one_episode_per_recognized_doc`
- [ ] `test_pipeline.py::test_single_unparseable_doc_does_not_abort_run`
- [ ] `test_pipeline.py::test_empty_corpus_publishes_nothing`
- [ ] `test_pipeline.py::test_report_accounts_for_every_walked_document`

## BDD Scenarios Covered

- "A full-corpus run publishes a typed episode for every recognized document"
- "A single unparseable document does not abort the corpus run"
- "A run over an empty corpus publishes nothing and completes cleanly"
- "A full re-index run makes no language-model call"

## Seam Tests

The following seam test validates the integration contract with the producer task. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify memory_episode_routing contract from TASK-RIP-002."""
import json

import pytest

from fleet_memory.payloads.registry import get_model_for_type


@pytest.mark.seam
@pytest.mark.integration_contract("memory_episode_routing")
def test_memory_episode_routing_format(published_episode):
    """Verify each published episode routes to the deterministic writer.

    Contract: content_format must be 'json' and payload_type a registered
    type so RelayService._ingest_json dispatches to the DeterministicWriter
    rather than the prose chunker.
    Producer: TASK-RIP-002
    """
    # Consumer side: verify format matches contract
    assert published_episode.content_format == "json", (
        f"Expected json routing, got: {published_episode.content_format}"
    )
    assert published_episode.payload_type, "payload_type must be set for json episodes"
    # payload_type must resolve through the registry (else relay DLQs as unknown type)
    model = get_model_for_type(published_episode.payload_type)
    rebuilt = model(**json.loads(published_episode.body))
    assert rebuilt.payload_type == published_episode.payload_type
```

## Implementation Notes

- Keep `reindex_corpus` pure with respect to transport: take the publisher
  (TASK-RIP-002) as a collaborator so unit tests inject a fake and assert on
  captured episodes — mirrors the handler/service separation idiom in the repo.
- The `RunReport` is the audit input for TASK-RIP-007; give it a stable shape
  (published natural_keys, unparseable[reason], unrecognized[reason]).
- Do not implement dedup/idempotency here — that is the writer's job downstream.
