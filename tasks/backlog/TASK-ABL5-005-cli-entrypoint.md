---
id: TASK-ABL5-005
title: Fixture CLI entrypoint scripts/fixture_snapshot.py
task_type: feature
parent_review: TASK-REV-ABL5
feature_id: FEAT-ABL-005
wave: 3
implementation_mode: task-work
complexity: 4
dependencies:
- TASK-ABL5-002
- TASK-ABL5-003
- TASK-ABL5-004
status: pending
tags:
- ablation
- fixture
- cli
- fleet-memory
consumer_context:
- task: TASK-ABL5-002
  consumes: create_snapshot / restore_fixture / FixtureManifest
  framework: fleet_memory.fixture.snapshot + .restore
  driver: Python API
  format_note: restore verifies content hash before touching the target; snapshot refuses overwrite; manifest returned for logging fixture id + hash
- task: TASK-ABL5-003
  consumes: apply_temporal_cut / CutResult
  framework: fleet_memory.fixture.temporal_cut
  driver: Python API
  format_note: cut date must be ISO date/datetime; InvalidCutDateError on anything else; CutResult carries excluded_after_cut / excluded_null / remaining
- task: TASK-ABL5-004
  consumes: discard_scratch / list_scratch_projects
  framework: fleet_memory.fixture.scratch
  driver: Python API
  format_note: rollout ids validated to [a-z0-9_]+; ScratchNamespaceError otherwise
---

# Task: Fixture CLI entrypoint scripts/fixture_snapshot.py

## Description

`scripts/fixture_snapshot.py` — the operator/adapter-facing argparse CLI over
the fixture package (the build plan's named entrypoint). Subcommands:

```
snapshot        --fixture-id v1 [--source-dsn DSN] [--fixtures-root PATH]
verify          --fixture-id v1 [--fixtures-root PATH]
restore         --fixture-id v1 --target-dsn DSN [--fixtures-root PATH]
cut             --target-dsn DSN --cut-date 2026-06-25 [--dry-run]
discard-scratch --target-dsn DSN --rollout-id run_01
list-scratch    --target-dsn DSN
```

- `--source-dsn` defaults to the `FLEET_MEMORY_PG_DSN` environment variable
  (the settings convention) so `snapshot` works on the GB10 without pasting
  credentials into argv; `--target-dsn` is always explicit — restore/cut/
  discard must never accidentally point at the live store via an ambient
  env var. Refuse (clear error, exit 2) if a required DSN is missing.
- `verify` recomputes the content hash and compares to the manifest: exit 0
  and print `fixture <id> OK sha256=<hash>` on match; exit 1 with a
  mismatch message otherwise (this is the round-trip validation primitive).
- `cut` prints the `CutResult` as single-line JSON on stdout
  (`{"excluded_after_cut": N, "excluded_null": N, "remaining": N}`) so the
  rollout adapter (FEAT-ABL-003) and validation scripts can parse it;
  `--dry-run` previews without deleting.
- `snapshot`/`restore` print fixture id + content hash + row counts on
  success (single-line JSON too — machine-readable throughout).
- Exit codes: 0 success; 1 fixture/tooling error (`FixtureError` subclasses,
  each printed as a one-line credential-free message on stderr); 2 usage
  error (argparse default).
- **No DSN, password, or credential fragment may ever reach stdout/stderr** —
  print the credential-free target label from the manifest/helpers instead.
- Entry point: `python scripts/fixture_snapshot.py <subcommand> ...` with
  `main(argv: list[str] | None = None) -> int` so tests drive it in-process.

## Acceptance Criteria

- [ ] All six subcommands parse and dispatch to the corresponding `fleet_memory.fixture` API (dispatch unit-tested with the package functions mocked)
- [ ] `snapshot` without `--source-dsn` falls back to `FLEET_MEMORY_PG_DSN`; missing both -> exit 2 with a clear message
- [ ] `restore`/`cut`/`discard-scratch`/`list-scratch` require `--target-dsn` explicitly (no env fallback)
- [ ] `verify` exits 0 on an intact fixture and 1 on a tampered one, message includes fixture id and expected/actual hashes
- [ ] `cut` emits single-line JSON with `excluded_after_cut`, `excluded_null`, `remaining`; `--dry-run` passes `dry_run=True` through
- [ ] `FixtureError` subclasses map to exit code 1 with one-line stderr messages; unexpected exceptions are not swallowed
- [ ] No DSN/password appears in any stdout/stderr output (test with a password-bearing DSN)
- [ ] New code only in `scripts/fixture_snapshot.py` (+ tests)
- [ ] All modified files pass project-configured lint/format checks with zero errors
- [ ] Unit tests green in the default suite (no Docker/Postgres — package APIs mocked)

## Test Requirements

Unit tests in `tests/unit/fixture/test_cli.py`: argument parsing matrix, env
fallback behaviour, dispatch + JSON output shape per subcommand (mock the
package functions), exit-code mapping, credential hygiene of all output.
Import the script as a module (`scripts/fixture_snapshot.py` — add a path
shim in the test or load via importlib) and call `main([...])` in-process.

## Implementation Notes

- Follow the existing `scripts/seed_df006.py` for script conventions if
  helpful, but keep this script thin — all logic lives in the package.
- JSON via `json.dumps(..., sort_keys=True)` for stable output.
