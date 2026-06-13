---
id: TASK-RIP-006
title: Backfill staging + sidecar operator review-gate
status: backlog
created: 2026-06-13 20:30:00+00:00
updated: 2026-06-13 20:30:00+00:00
priority: high
task_type: feature
parent_review: TASK-REV-RIP7
feature_id: FEAT-MEM-07
wave: 5
implementation_mode: task-work
complexity: 5
estimated_minutes: 75
dependencies:
- TASK-RIP-002
- TASK-RIP-005
tags:
- reindex
- backfill
- review-gate
- security
- integration-contract
consumer_context:
- task: TASK-RIP-002
  consumes: memory_episode_routing
  framework: "FastStream NatsBroker / RelayService.ingest content_format routing"
  driver: "nats-core MemoryEpisodeV1 publisher"
  format_note: "content_format must be 'json' and payload_type a registered type; reviewed backfill publishes through the SAME publisher — no second write path"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Backfill staging + sidecar operator review-gate

## Description

Walk `backfill/staging/` for Fable-authored payloads and publish each **only when
an operator-controlled sidecar review marker exists for it** — a marker held
*outside* the payload content (ASSUM-003). Reviewed backfill reuses the same
publisher (TASK-RIP-002) and the same relay path as deterministic re-index:
**one write path, byte-identical** (DECISION-DF-001 keeps Fable strictly offline;
nothing on this publish path is frontier-authored at runtime). A payload that
asserts its own review status *in its content* is still gated — only the operator
marker counts.

The review gate is a **sidecar marker file** (e.g. `<payload>.reviewed`) next to
the staged payload — git-trackable, per-payload, and impossible for a payload to
self-grant.

This task is a **consumer** of the §4 contract `memory_episode_routing`.

## Acceptance Criteria

- [ ] A backfill staging dir setting (`FLEET_MEMORY_BACKFILL_DIR`, default `backfill/staging/`) is added to `Settings`
- [ ] A staged payload **with** an operator review marker present is published through the same relay path and stored as a typed record like any deterministically parsed payload
- [ ] A staged payload **without** a review marker is not published
- [ ] A staged payload whose own content claims it has been reviewed, but for which no operator marker exists, is **not** published (self-assertion cannot bypass the gate)
- [ ] Reviewed backfill publishes via the same publisher/relay path as deterministic re-index — no second write code path
- [ ] `tests/unit/reindex/test_backfill.py` covers: reviewed publishes, unreviewed gated, self-asserted-but-unmarked gated
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_backfill.py::test_reviewed_payload_publishes`
- [ ] `test_backfill.py::test_unreviewed_payload_gated`
- [ ] `test_backfill.py::test_self_asserted_review_without_marker_gated`

## BDD Scenarios Covered

- "A reviewed backfill payload is published on the next run"
- "An unreviewed backfill payload is not published"
- "A backfill payload that claims to be reviewed within its own content is still gated"
- "Reviewed backfill payloads publish through the same relay path as deterministically parsed documents"

## Seam Tests

The following seam test validates the integration contract with the producer task. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify memory_episode_routing contract from TASK-RIP-002 (backfill path)."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("memory_episode_routing")
def test_reviewed_backfill_uses_same_routing(published_backfill_episode):
    """Reviewed backfill publishes byte-identically to deterministic re-index.

    Contract: content_format == 'json' + payload_type set, via the SAME
    publisher (TASK-RIP-002) — no second write path.
    Producer: TASK-RIP-002
    """
    assert published_backfill_episode.content_format == "json"
    assert published_backfill_episode.payload_type, "payload_type must be set"
```

## Implementation Notes

- The marker check is the gate's whole security model: read the marker from the
  filesystem next to the payload, never from inside the payload body. This makes
  "a payload that claims it is reviewed" structurally unable to publish itself.
- Do not introduce a parallel publisher — import and call TASK-RIP-002's publisher
  so the "single write path" invariant holds by construction.
