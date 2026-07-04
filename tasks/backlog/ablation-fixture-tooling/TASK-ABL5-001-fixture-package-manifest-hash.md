---
id: TASK-ABL5-001
title: Fixture package scaffolding - manifest, content hash, error taxonomy
task_type: feature
parent_review: TASK-REV-ABL5
feature_id: FEAT-ABL-005
wave: 1
implementation_mode: task-work
complexity: 4
dependencies: []
status: blocked
tags:
- ablation
- fixture
- fleet-memory
autobuild_state:
  current_turn: 3
  max_turns: 8
  worktree_path: /home/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-ABL-005
  base_branch: main
  started_at: '2026-07-04T07:39:06.868745'
  last_updated: '2026-07-04T07:55:30.202248'
  turns:
  - turn: 1
    decision: feedback
    feedback: '- The implementation of the fixture package (manifest, hashing, error
      taxonomy) is missing. The player only modified an __init__.py file and created
      no new files or tests.: Implement the required logic in src/fleet_memory/fixture/
      and provide corresponding unit tests.

      - Evidence collection aborted with status ''partial_gate_abort''. Tests failed
      or could not be run due to a substrate error (FileNotFoundError in pytest temp
      directory).: Ensure the environment is stable and that all required files are
      present so that the test-orchestrator can complete its run.'
    timestamp: '2026-07-04T07:39:06.868745'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
  - turn: 2
    decision: feedback
    feedback: '- The test execution failed with a TypeError: ''expected string or
      bytes-like object, got PosixPath''. This prevented the orchestrator from completing
      the verification cycle.: Ensure that any path-related logic in the implementation
      or tests handles both strings and Path objects, or explicitly casts Path objects
      to strings before passing them to functions expecting bytes/strings.

      - Gathering status is ''partial_gate_abort''. Coverage and BDD evidence are
      missing.: Resolve the test execution error to allow the orchestrator to complete
      the gathering phase and provide coverage metrics.'
    timestamp: '2026-07-04T07:44:56.931172'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
  - turn: 3
    decision: feedback
    feedback: "- Deterministic honesty record (claim_audit_unmodified, severity=should_fix):\
      \ Player claim: Player claimed file src/fleet_memory/fixture/__init__.py. Actual:\
      \ Path is tracked in git but 'git status --porcelain' shows no change for it\
      \ \u2014 the Player claimed work on a file it did not actually modify this turn.\
      \ Most likely cause: the report writer swept an orchestrator-managed path (e.g.\
      \ a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n- Deterministic honesty record (claim_audit_unmodified,\
      \ severity=should_fix): Player claim: Player claimed file src/fleet_memory/mcp/server.py.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n- Deterministic honesty record (claim_audit_unmodified,\
      \ severity=should_fix): Player claim: Player claimed file tests/conftest.py.\
      \ Actual: Path is tracked in git but 'git status --porcelain' shows no change\
      \ for it \u2014 the Player claimed work on a file it did not actually modify\
      \ this turn. Most likely cause: the report writer swept an orchestrator-managed\
      \ path (e.g. a file under .guardkit/autobuild/ or tasks/<state>/) into files_modified.\
      \ Defence-in-depth for the agent_invoker-side filter; this is a warning, not\
      \ a turn-rejecting fabrication..\n... and 3 more issues"
    timestamp: '2026-07-04T07:52:12.373161'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
---

# Task: Fixture package scaffolding - manifest, content hash, error taxonomy

## Description

Create the new package `src/fleet_memory/fixture/` (this feature's ONLY
allowed code locations are this package and `scripts/fixture_snapshot.py` —
the store/retrieval stack is the ablation's subject and MUST NOT be touched,
scope §7). This task lays the foundation the other tasks build on:

1. `src/fleet_memory/fixture/__init__.py` — public API re-exports.
2. `src/fleet_memory/fixture/errors.py` — error taxonomy, all inheriting a
   base `FixtureError(Exception)`:
   - `UnknownFixtureError` (fixture id not found under the fixtures root)
   - `FixtureHashMismatchError` (recomputed content hash != manifest hash)
   - `InvalidCutDateError` (missing/unparseable temporal-cut date)
   - `ScratchNamespaceError` (invalid rollout id / scratch namespace)
   Error messages MUST be credential-free: never interpolate a DSN — name
   host:port/db only (follow the `_dsn_target` pattern in
   `src/fleet_memory/store.py:35-49`; implement a small local equivalent in
   the fixture package rather than importing the private helper).
3. `src/fleet_memory/fixture/manifest.py` — `FixtureManifest` (Pydantic v2
   model, the repo standard):
   - `fixture_id: str` (must match `^[a-z0-9_.-]+$`, non-empty)
   - `created_at: str` (ISO-8601 UTC; informational — NEVER part of the hash)
   - `source_target: str` (credential-free `host:port/db` label)
   - `content_hash: str` (SHA-256 hex digest of the fixture payload files)
   - `table_row_counts: dict[str, int]`
   - `null_occurred_at_count: int` (entries whose
     `value->'episode_meta'->>'occurred_at'` is NULL or absent; on the live
     store this was verified as 176 on 2026-07-03 — the count is snapshot
     metadata, NOT a code constant)
   - `pg_dump_version: str`
   Functions:
   - `write_manifest(manifest, fixture_dir)` / `read_manifest(fixture_dir)`
     (JSON, `manifest.json`, sorted keys, UTF-8) — `read_manifest` raises
     `UnknownFixtureError` if the directory or file is missing.
   - `compute_content_hash(fixture_dir) -> str` — SHA-256 over the bytes of
     every payload file in the fixture directory EXCEPT `manifest.json`,
     concatenated in sorted relative-path order (each file preceded by its
     relative path + NUL byte so renames change the hash). Deterministic and
     independent of mtime/ctime.
   - `fixture_dir(fixtures_root, fixture_id) -> Path` — path helper; rejects
     ids that fail the pattern (no path traversal).

Default fixtures root: `eval/fixtures/` (configurable by callers; later CLI
flag). Add `eval/fixtures/` to `.gitignore` — fixture content derives from
the live store and must never be committed.

## Acceptance Criteria

- [ ] `from fleet_memory.fixture import FixtureManifest, compute_content_hash, read_manifest, write_manifest` works, plus the four error types
- [ ] `compute_content_hash` returns the same digest for the same file bytes regardless of file mtimes and of creation order, and a different digest when any payload byte or filename changes
- [ ] `manifest.json` is excluded from its own hash (writing the manifest does not invalidate the hash)
- [ ] `read_manifest` on a missing fixture directory raises `UnknownFixtureError` naming the fixture id (not any path secrets)
- [ ] Manifest JSON round-trips: `write_manifest` then `read_manifest` yields an equal model
- [ ] Invalid `fixture_id` (empty, path separators, `..`) is rejected with a clear error
- [ ] No file outside `src/fleet_memory/fixture/`, `tests/`, and `.gitignore` is created or modified
- [ ] All modified files pass project-configured lint/format checks with zero errors
- [ ] Unit tests cover: hash determinism, hash sensitivity (content + filename), manifest round-trip, missing-fixture error, fixture-id validation

## Test Requirements

Unit tests in `tests/unit/fixture/test_manifest.py` (create
`tests/unit/fixture/__init__.py`). Pure filesystem via `tmp_path` — no
database, no network. Must run inside the default suite
(`pytest tests/ -m "not integration"`).

## Implementation Notes

- Pydantic v2 (`pydantic>=2`) is already a project dependency; follow the
  style of `src/fleet_memory/relay/schema.py` for model definitions.
- Hash framing: `sha256(b"".join(rel_path.encode() + b"\x00" + file_bytes for each payload file sorted by rel_path))`.
- Keep this task free of any Postgres interaction — snapshot/restore (TASK-ABL5-002)
  owns that.
