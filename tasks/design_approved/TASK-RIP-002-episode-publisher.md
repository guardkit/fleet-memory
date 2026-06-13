---
complexity: 5
created: 2026-06-13 20:30:00+00:00
dependencies: []
estimated_minutes: 60
feature_id: FEAT-MEM-07
id: TASK-RIP-002
implementation_mode: task-work
parent_review: TASK-REV-RIP7
priority: high
status: design_approved
tags:
- reindex
- relay
- publisher
- integration-contract
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: Episode publisher helper (MemoryEpisodeV1 json + payload_type)
updated: 2026-06-13 20:30:00+00:00
wave: 1
---

# Task: Episode publisher helper (MemoryEpisodeV1 json + payload_type)

## Description

A thin publisher that turns a constructed `BasePayload` into a `MemoryEpisodeV1`
with `content_format="json"` and an explicit `payload_type`, serializes the
payload to the JSON `body`, sets `source_ref`, and publishes it onto the MEMORY
stream via the nats-core broker/publisher helper. **This is the single write
path.** It contains no business logic and no dedup — idempotency, versioned
upsert, and natural-key dedup are enforced downstream by the
`DeterministicWriter`'s content-hash upsert. It must make **no LLM / cloud /
frontier-model call** (DECISION-DF-001).

This task is the **producer** of the §4 Integration Contract `memory_episode_routing`.

## Acceptance Criteria

- [ ] `src/fleet_memory/reindex/publisher.py` exposes a publisher that accepts a `BasePayload` and publishes a `MemoryEpisodeV1` onto the MEMORY stream
- [ ] The published episode has `content_format == "json"` and `payload_type == payload.payload_type`, so `RelayService._ingest_json` routes it to the `DeterministicWriter` rather than the prose chunker ([relay/service.py](src/fleet_memory/relay/service.py))
- [ ] `body` is the payload's canonical JSON serialization and round-trips: `get_model_for_type(episode.payload_type)(**json.loads(episode.body))` reconstructs an equal payload
- [ ] `source_ref` carries the source document reference; `episode_id` is derived deterministically from the payload `natural_key` (so a re-publish of the same parsed document is idempotent at the JetStream Msg-Id layer as well as downstream)
- [ ] No language-model, cloud, or frontier-model request is made by the publisher (asserted by test — e.g. no network egress / no LLM client constructed)
- [ ] `tests/unit/reindex/test_publisher.py` asserts content_format, payload_type, body round-trip, and deterministic episode_id
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `test_publisher.py::test_episode_is_json_with_payload_type`
- [ ] `test_publisher.py::test_body_round_trips_through_registry`
- [ ] `test_publisher.py::test_episode_id_deterministic_for_natural_key`
- [ ] Use a fake/in-memory broker (TestNatsBroker idiom) — no live NATS in unit tests

## BDD Scenarios Covered

- "Published episodes are structured so the relay routes them to the deterministic writer"
- "Publishing the same parsed document twice yields a single stored record" (publish-layer contribution)
- "The re-index pipeline invokes no cloud or frontier model" (publish side)

## Implementation Notes

- The routing contract is the whole point: `content_format` must be the literal
  string `"json"` and `payload_type` must be a key in
  [payloads/registry.py](src/fleet_memory/payloads/registry.py). Any other
  content_format sends the episode down the prose chunker — a silent wrong-path bug.
- Reuse the existing broker/publisher wiring from [app.py](src/fleet_memory/app.py);
  do not create a second broker.
- Serialize with `payload.model_dump(mode="json")` and dump with sorted keys to
  keep the body stable across runs.