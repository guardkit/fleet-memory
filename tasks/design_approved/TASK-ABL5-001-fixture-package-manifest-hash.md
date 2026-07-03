---
autobuild_state:
  base_branch: main
  current_turn: 3
  last_updated: '2026-07-03T17:39:06.938528'
  max_turns: 5
  started_at: '2026-07-03T17:38:36.497401'
  turns:
  - coach_success: true
    decision: feedback
    feedback: '- Direct-mode evidence gate blocked the turn (direct_mode_ac_unverified).
      Direct mode relaxes coverage/arch gates but still requires verifiable AC delivery,
      resolved wiring, and runnable registered producers:

      - [direct_mode_ac_unverified] Direct mode: 6/9 acceptance criteria have no disk
      evidence (unmet: [''AC-002'', ''AC-005'', ''AC-006'', ''AC-007'', ''AC-008'',
      ''AC-009'']). Direct mode relaxes coverage/arch but NOT AC delivery.'
    player_success: true
    player_summary: '[RECOVERED via git_test_detection] Original error: Unexpected
      error executing task-work: LangGraphHarness: failed to construct DeepAgent for
      role=''player'' model=''openai:claude-sonnet-4-5-20250929'': Missing credentials.
      Please pass an `api_key`, `workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY`
      or `OPENAI_ADMIN_KEY` environment variable.'
    timestamp: '2026-07-03T17:38:36.497401'
    turn: 1
  - coach_success: true
    decision: feedback
    feedback: '- Direct-mode evidence gate blocked the turn (direct_mode_ac_unverified).
      Direct mode relaxes coverage/arch gates but still requires verifiable AC delivery,
      resolved wiring, and runnable registered producers:

      - [direct_mode_ac_unverified] Direct mode: 6/9 acceptance criteria have no disk
      evidence (unmet: [''AC-002'', ''AC-005'', ''AC-006'', ''AC-007'', ''AC-008'',
      ''AC-009'']). Direct mode relaxes coverage/arch but NOT AC delivery.'
    player_success: true
    player_summary: '[RECOVERED via git_test_detection] Original error: Unexpected
      error executing task-work: LangGraphHarness: failed to construct DeepAgent for
      role=''player'' model=''openai:claude-sonnet-4-5-20250929'': Missing credentials.
      Please pass an `api_key`, `workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY`
      or `OPENAI_ADMIN_KEY` environment variable.'
    timestamp: '2026-07-03T17:38:46.946411'
    turn: 2
  - coach_success: true
    decision: feedback
    feedback: '- Direct-mode evidence gate blocked the turn (direct_mode_ac_unverified).
      Direct mode relaxes coverage/arch gates but still requires verifiable AC delivery,
      resolved wiring, and runnable registered producers:

      - [direct_mode_ac_unverified] Direct mode: 9/9 acceptance criteria have no disk
      evidence (unmet: [''AC-001'', ''AC-002'', ''AC-003'', ''AC-004'', ''AC-005'',
      ''AC-006'', ''AC-007'', ''AC-008'', ''AC-009'']). Direct mode relaxes coverage/arch
      but NOT AC delivery.'
    player_success: true
    player_summary: '[RECOVERED via git_test_detection] Original error: Unexpected
      error executing task-work: LangGraphHarness: failed to construct DeepAgent for
      role=''player'' model=''openai:claude-sonnet-4-5-20250929'': Missing credentials.
      Please pass an `api_key`, `workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY`
      or `OPENAI_ADMIN_KEY` environment variable.'
    timestamp: '2026-07-03T17:38:56.928810'
    turn: 3
  worktree_path: /home/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-ABL-005
complexity: 4
dependencies: []
feature_id: FEAT-ABL-005
id: TASK-ABL5-001
implementation_mode: task-work
parent_review: TASK-REV-ABL5
status: design_approved
tags:
- ablation
- fixture
- fleet-memory
task_type: feature
title: Fixture package scaffolding - manifest, content hash, error taxonomy
wave: 1
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