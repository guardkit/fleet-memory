# Retro: FEAT-MEM-05 AutoBuild Run

**Feature:** Retrieval API + Context Assembly (complexity 7, 7 tasks)
**Run date:** 2026-06-13
**Outcome:** SUCCESS after recovery — 7/7 tasks completed, merged to `main` (`bb92ed2`), 363/363 unit tests green.

This retro documents the errors encountered during the autonomous build and the
`/feature-complete` merge, with root causes and the fixes applied, so the next
run can avoid or quickly diagnose them.

---

## Summary

| Phase | What happened | Severity | Resolution |
|-------|---------------|----------|------------|
| Wave 3 build | TASK-RA-003 hit `unrecoverable_stall` after 3 turns | **Blocking** | Installed missing dep into Coach venv, `--resume` |
| Merge (`/feature-complete`) | `git merge` aborted — pre-existing uncommitted edits on `main` | Blocking | Stashed the two paths, merged, restored |
| Throughout | Trailing FalkorDB `no running event loop` traceback | Noise | None needed — benign teardown |
| Finalize | `guardkit autobuild complete` / `worktree cleanup` did not perform merge/cleanup | Minor | Did merge + worktree removal by hand |

The build never had a genuine code defect. Both blocking failures were
environmental / harness-level.

---

## Error 1 — Stale Coach venv caused an unrecoverable stall (TASK-RA-003)

### Symptom
Wave 3 (TASK-RA-003, "Token-budgeted assembly and coverage") failed after 3
turns with:

```
Status: UNRECOVERABLE_STALL
context_pollution_stall_no_checkpoint
Unrecoverable stall detected after 3 turn(s).
```

The Coach rejected **all 10 acceptance criteria** on every turn with the same
note:

```
Cannot verify - independent tests failed to collect due to missing tiktoken dependency
```

The deterministic honesty gate also flagged several `should_fix` warnings
(Player claimed files like `pyproject.toml` were modified but `git status`
showed no change) — these were a red herring, not the cause.

### Root cause
TASK-RA-003 introduced a **new runtime dependency**, `tiktoken` (used for token
counting in `src/fleet_memory/retrieval/assembly.py`), and correctly added it to
`pyproject.toml`. But the Coach's bootstrap venv
(`.guardkit/worktrees/FEAT-MEM-05/.venv`) had been provisioned **once at feature
start**, before that dependency existed. Nothing reinstalls into the existing
venv mid-feature, so the Coach's independent `pytest` run hit
`ModuleNotFoundError: tiktoken`, could not collect the suite, and rejected every
AC. Three identical rejections with no passing checkpoint to roll back to →
`context_pollution_stall_no_checkpoint`.

The Player's implementation was actually correct: its own 14 tests passed in its
own environment, and an independent full run of `tests/unit` passed **321/321**
once `tiktoken` was installed.

### Fix
```bash
cd .guardkit/worktrees/FEAT-MEM-05
.venv/bin/python -m pip install -e '.[dev]'   # quote extras in zsh
guardkit autobuild feature FEAT-MEM-05 --resume
```
`--resume` re-bootstrapped the venv (picking up the now-committed `tiktoken`),
correctly **skipped** the already-`completed` waves 1–2, and re-ran TASK-RA-003,
which the Coach approved on turn 1. Waves 4–5 then completed cleanly. Net result:
7/7 SUCCESS, 363 unit tests green.

### Prevention / lessons
- When a task adds a dependency, the Coach verification venv must be refreshed
  before that task's Coach turn. Workaround today: install into the worktree
  venv and `--resume`.
- **Ground-truth before blaming the Player.** On any "tests failed to collect"
  signal, run the pinned test command directly in the worktree venv first.
- `should_fix` honesty warnings about orchestrator-managed paths
  (`.claude/task-plans/…`, `tasks/<state>/…`) swept into `files_modified` are
  warnings, not turn-rejecting fabrications — don't chase them as the cause.

---

## Error 2 — Merge blocked by pre-existing uncommitted changes on `main`

### Symptom
During `/feature-complete`, `git merge --no-ff autobuild/FEAT-MEM-05` aborted:

```
error: Your local changes to the following files would be overwritten by merge:
  .guardkit/graphiti-query-log.jsonl
  features/retrieval-api/retrieval-api.feature
Merge with strategy ort failed.
```

### Root cause
`main` carried **pre-existing uncommitted edits** (present before this session):
an unstaged append to the runtime log `.guardkit/graphiti-query-log.jsonl` and a
31-line **staged** addition to `features/retrieval-api/retrieval-api.feature`.
Neither file is modified by the feature branch (verified: branch content for both
equals the merge-base, which was `main`'s HEAD), so the merged result for them
is byte-identical to HEAD. Git still refuses, because materializing the merge
result would overwrite the dirty working-tree/index entries.

### Fix
Non-destructive stash of just those two paths, then merge, then restore:
```bash
git stash push -m "preserve pre-existing local edits" -- \
  .guardkit/graphiti-query-log.jsonl features/retrieval-api/retrieval-api.feature
git merge --no-ff autobuild/FEAT-MEM-05 -m "Merge FEAT-MEM-05: …"
git stash pop
```
Both files were restored with content intact. (Side effect: the `.feature`
change came back **unstaged** rather than staged — content preserved, staging
state cosmetic.)

### Prevention / lessons
- This repo is frequently under concurrent modification by other agent sessions;
  expect a dirty `main` and unrelated work in `git status`.
- Inspect *which* files actually conflict and whether the branch even touches
  them before stashing/overwriting — a path-scoped `git stash push -- <paths>`
  preserves unrelated user work.
- Re-check mergeability immediately before merging, not before pausing to ask.

---

## Error 3 — Benign FalkorDB / Graphiti teardown traceback

### Symptom
After the feature reported `status=completed`, the log ended with:

```
ERROR:graphiti_core.driver.falkordb_driver:Error executing FalkorDB query: no running event loop
…
RuntimeError: no running event loop
```

### Assessment
Post-orchestration teardown noise — the async FalkorDB client is torn down after
its event loop has closed. It appears **after** the success summary and does not
affect the build result. **Not a failure signal.** No action needed.

---

## Error 4 — `complete` / `worktree cleanup` are placeholders in this CLI version

### Symptom
- `guardkit autobuild complete FEAT-MEM-05` only printed a "READY FOR MERGE"
  handoff panel; it did **not** merge, archive, move task files, or clean up.
- `guardkit worktree cleanup FEAT-MEM-05` → `Unknown command: worktree`.

### Resolution
Performed finalization by hand:
```bash
git merge --no-ff autobuild/FEAT-MEM-05 -m "…"
git worktree remove .guardkit/worktrees/FEAT-MEM-05
git worktree prune
git branch -d autobuild/FEAT-MEM-05
```

### Lessons
- In this version, treat `/feature-complete` as "verify + print instructions";
  do the git merge, `git worktree remove`, and `git branch -d` manually.
- Task-state files were left as the build produced them: the merge brought the RA
  task `.md` files into `tasks/design_approved/`, while untracked copies remain in
  `tasks/backlog/retrieval-api/`. The CLI's task-move-to-`completed` step is a
  placeholder, so these were not reconciled.

---

## Verification performed

- Worktree venv, full unit suite after dep install: **321/321 passed** (pre-resume).
- Worktree, post-build full unit suite: **363/363 passed**.
- `main`, post-merge full unit suite: **363/363 passed**, `tiktoken` present in
  `pyproject.toml`.

## Deliverables landed on `main`

6 retrieval modules — `search_request.py`, `core.py`, `assembly.py`,
`composition.py`, `probe_harness.py`, `__init__.py` — plus the unit and
integration test suites. Merge commit `bb92ed2`. Not yet pushed to origin.
