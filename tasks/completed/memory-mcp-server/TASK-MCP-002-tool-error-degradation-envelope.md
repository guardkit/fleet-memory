---
complexity: 4
consumer_context:
- consumes: ServerContext
  driver: fastmcp
  format_note: Tools receive the wired ServerContext (store, writer, settings) built
    lazily in the lifespan
  framework: FastMCP (stdio server)
  task: TASK-MCP-001
created: 2026-06-13 16:30:00+00:00
dependencies:
- TASK-MCP-001
estimated_minutes: 50
feature_id: FEAT-MEM-06
id: TASK-MCP-002
implementation_mode: task-work
parent_review: TASK-REV-MEM06
priority: high
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-MEM-06 completed"
pre_sweep_status: design_approved
tags:
- mcp
- degradation
- error-handling
- reliability
task_type: feature
test_results:
  coverage: null
  last_run: null
  status: pending
title: Shared tool-error envelope and graceful-degradation helper
updated: 2026-06-13 16:30:00+00:00
wave: 2
---

# Task: Shared tool-error envelope and graceful-degradation helper

## Description

Provide the single reliability primitive every MCP tool uses: a structured
**tool-error envelope** and a `@tool_safe`-style wrapper that catches store /
embedding outages and turns them into structured tool-error results instead of
crashing the server. This is the cross-cutting concern that satisfies the
feature's headline reliability AC — "tool failures are surfaced as structured
tool-error results so the server degrades gracefully (no crash)".

The wrapper maps the known upstream exceptions to caller-facing messages:

| Upstream exception (source) | Tool-error message |
|---|---|
| `TimeoutError` (store unreachable, [retrieval/core.py], [store.py]) | "the memory store is unavailable" |
| `EmbedServiceError` / `EmbedTimeoutError` ([errors.py]) | "search is temporarily unavailable" (read) / "the write could not be completed" (write) |
| `ValueError` / `NamespaceValidationError` / `UnknownPayloadTypeError` ([errors.py]) | the validation message, surfaced as a client-error tool result |

Messages must preserve credential hygiene — never echo DSNs, hosts, or secrets
(the upstream layers already strip these; do not re-introduce them).

## Acceptance Criteria

- [ ] `src/fleet_memory/mcp/degradation.py` exists exposing a structured tool-error result type and a `tool_safe` decorator (or equivalent context wrapper)
- [ ] A wrapped tool that raises `TimeoutError` returns a structured tool-error result whose message states the memory store is unavailable, and the wrapper does not re-raise (server stays running)
- [ ] A wrapped tool that raises `EmbedServiceError` returns a structured tool-error result whose message states the operation is temporarily unavailable / could not be completed
- [ ] A wrapped tool that raises a validation `ValueError` returns a structured client-error result carrying the validation message (distinguishable from an infrastructure-degradation result)
- [ ] No tool-error message contains a DSN, host, port, or credential substring (assert against a representative error)
- [ ] `tests/unit/test_mcp_degradation.py` covers all three exception classes and the no-crash guarantee
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_mcp_degradation.py::test_store_timeout_returns_unavailable`
- [ ] `tests/unit/test_mcp_degradation.py::test_embed_error_returns_temporarily_unavailable`
- [ ] `tests/unit/test_mcp_degradation.py::test_validation_error_returns_client_error`
- [ ] `tests/unit/test_mcp_degradation.py::test_wrapper_never_reraises` (server-stays-running guarantee)
- [ ] `tests/unit/test_mcp_degradation.py::test_messages_have_no_credentials`

## BDD Scenarios Covered

- (Enabling primitive for the degradation scenarios realized in TASK-MCP-003/004)

## Seam Tests

The following seam test validates the integration contract with the producer task. Implement this test to verify the boundary before integration.

```python
"""Seam test: verify ServerContext contract from TASK-MCP-001."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("ServerContext")
def test_server_context_shape():
    """Verify ServerContext exposes the fields tools depend on.

    Contract: ServerContext carries store, writer, settings (built lazily).
    Producer: TASK-MCP-001
    """
    from fleet_memory.mcp.server import ServerContext

    # Consumer side: the envelope and tools only read these attributes.
    for field in ("store", "writer", "settings"):
        assert field in ServerContext.__dataclass_fields__, (
            f"ServerContext must expose '{field}'"
        )
```

## Implementation Notes

- Exception sources are concrete: see [errors.py](src/fleet_memory/errors.py)
  (`EmbedServiceError`, `EmbedTimeoutError`, `NamespaceValidationError`,
  `UnknownPayloadTypeError`) and the `TimeoutError` raised by the retrieval/store
  layers when Postgres is unreachable.
- Distinguish **infrastructure degradation** (retryable, "unavailable") from
  **client error** (validation, "you sent something invalid") in the result shape
  so tools and tests can assert on the category.
- Keep this module dependency-light so all four Wave-3 tasks can import it without
  pulling in tool-specific code.