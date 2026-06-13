# Feature Spec Summary: Memory MCP Server

**Stack**: python
**Generated**: 2026-06-13T15:12:43Z
**Scenarios**: 31 total (6 smoke, 3 regression)
**Assumptions**: 9 total (4 high / 3 medium / 2 low confidence)
**Review required**: Yes

## Scope

Covers the FEAT-MEM-06 FastMCP server module: the `memory_search`,
`memory_write_payload` and `memory_supersede` tools layered over the FEAT-MEM-05
retrieval API and the FEAT-MEM-03 deterministic writer, plus a project-listing
resource, served over stdio for Claude Desktop as a drop-in replacement for the
Graphiti MCP. The write tools dispatch through the same typed registry + writer —
there is no second write path — so MCP writes are byte-identical in store form to
relay writes of the same payload. Tool failures are surfaced as structured
tool-error results so the server degrades gracefully (no crash) when Postgres or
the embedding service is unreachable.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 7 |
| Boundary conditions (@boundary) | 5 |
| Negative cases (@negative) | 9 |
| Edge cases (@edge-case) | 13 |

(Tags overlap: one boundary scenario and three edge cases are also tagged
`@negative`; the three `@regression` scenarios are all edge cases.)

## Deferred Items

None — all four proposed groups and all six edge-case-expansion scenarios
(security, concurrency, integration boundaries) were accepted.

Out of scope by upstream decision (per build-plan OD-3): the thin library client
that guardkit's read-path cutover (FEAT-MEM-08) uses — MCP stays a Desktop surface.
HTTP/SSE transports are also out of scope for this feature (stdio only).

## Open Assumptions (low confidence)

These two need human verification before the spec is treated as settled:

- **ASSUM-004** — the project-listing resource URI is `memory://projects` (confirm
  against the FastMCP resource conventions adopted from the `fastmcp-python`
  template reference).
- **ASSUM-005** — `memory_supersede` rejects an empty predecessor list rather than
  silently no-opping (the underlying `apply_supersessions()` returns early on
  empty; the tool-boundary contract is a deliberate choice to confirm).

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Memory MCP Server" \
      --context features/memory-mcp-server/memory-mcp-server_summary.md

`/feature-plan` Step 11 will link these scenarios to the tasks it creates by
inserting `@task:<TASK-ID>` tags; none are present yet (feature-spec is link-free
by design).
