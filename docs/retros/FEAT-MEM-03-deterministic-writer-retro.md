# Retro: FEAT-MEM-03 AutoBuild Run

**Feature:** Deterministic Writer (complexity 6, 5 tasks)
**Run date:** 2026-06-13
**Outcome:** SUCCESS, clean — 5/5 tasks coach-approved on turn 1, merged to `main`
(`c6c6983`), finalized (`201f09d`), 73/73 writer unit tests green.

This was a **clean run with zero blocking failures and zero tracebacks** — every
task was approved on its first turn and the smoke gate passed. This retro records
the non-blocking warnings emitted during the build and the post-run tooling
quirks hit during `/feature-complete`, so the next run can recognise them as
noise rather than chase them.

---

## Summary

| Phase | What happened | Severity | Resolution |
|-------|---------------|----------|------------|
| Build (all waves) | `tree_sitter_language_pack` missing → 39× wiring-analysis parse failures | Noise | None — factory wiring analysis degraded gracefully |
| Build (Wave 1 init) | Graphiti FalkorDB workaround skipped ("decorator source changed unexpectedly") | Noise | None — flagged for manual review, no runtime impact |
| Build (startup) | Pydantic V1 / Python 3.14 incompatibility `UserWarning` | Noise | None — benign langchain_core deprecation |
| Build (every Coach turn) | `test-orchestrator` SDK timeout capped 1499s → 600s (5×) | Informational | None — by-design cap (TASK-FIX-SPECHANG) |
| Finalize (`/feature-complete`) | `complete` is a handoff; `worktree cleanup` unknown command; `worktree remove` needed `--force` | Minor | Did merge + worktree removal + task moves by hand |

No genuine code defect, no stall, no merge conflict, no Coach rejection. All five
findings are environmental / harness-level.

---

## Error 1 — `tree_sitter_language_pack` missing → wiring-analysis parse failures

### Symptom
Repeated **39 times** across all waves, during the factory's wiring analysis:

```
WARNING:guardkitfactory.wiring.parser:Parse failed for language 'python':
tree_sitter_language_pack is required for wiring analysis.
Install it with: pip install tree-sitter-language-pack
```

### Root cause
`guardkitfactory`'s wiring analysis uses Tree-sitter to parse Python for
structural/dependency wiring checks. The optional `tree-sitter-language-pack`
grammar bundle is not installed in the run environment, so every parse attempt
short-circuits with this warning.

### Assessment / resolution
Non-blocking. The analysis degrades gracefully — the Player/Coach loop, tests,
and quality gates all ran normally and approved every task. No action was needed
for this build.

### Prevention / lessons
- If wiring analysis is wanted as a real signal, install the grammar pack in the
  environment: `pip install tree-sitter-language-pack`.
- Otherwise treat these 39 lines as expected noise — they do **not** indicate a
  problem with the generated code.

---

## Error 2 — Graphiti FalkorDB workaround skipped

### Symptom
Once, during Wave 1 orchestrator init:

```
WARNING:guardkit.knowledge.falkordb_workaround:[Graphiti] FalkorDB decorator
source changed unexpectedly, skipping workaround (manual review needed)
```

### Root cause
GuardKit applies a runtime monkey-patch ("workaround") to a FalkorDB/Graphiti
decorator. It guards itself by inspecting the decorator's source; when that
source no longer matches the expected shape (an upstream version drift), it
**skips** the patch rather than risk patching the wrong thing.

### Assessment / resolution
Non-blocking for this run — context loading and the build completed normally. The
"manual review needed" note is a maintenance flag for the GuardKit harness, not a
failure of this feature's build.

### Prevention / lessons
- Flag for the GuardKit maintainers: the FalkorDB workaround needs re-aligning to
  the current Graphiti/FalkorDB version so the patch re-engages.
- Unrelated to FEAT-MEM-03 code; safe to ignore for this feature.

---

## Error 3 — Pydantic V1 / Python 3.14 incompatibility warning

### Symptom
Emitted once at process startup:

```
.../langchain_core/_api/deprecation.py:25: UserWarning: Core Pydantic V1
functionality isn't compatible with Python 3.14 or greater.
```

### Root cause
The run uses the system interpreter at
`/Library/Frameworks/Python.framework/Versions/3.14`, and a transitive
dependency (`langchain_core`) still imports Pydantic v1 compatibility shims,
which warn under Python ≥ 3.14.

### Assessment / resolution
Benign warning, not an error — fleet-memory's own code uses Pydantic v2. No impact
on the build.

### Prevention / lessons
- Known environment quirk (see auto-memory "GuardKit AutoBuild quirks"). Expect
  this line on every run under the 3.14 framework interpreter.

---

## Error 4 — `test-orchestrator` specialist SDK timeout capped (informational)

### Symptom
Five times (once per task's Coach/specialist phase):

```
INFO:guardkit.orchestrator.specialist_invocations:[TASK-DW-00X] test-orchestrator
sdk_timeout capped from 1499s to 600s (TASK-FIX-SPECHANG)
```

### Assessment
This is an **INFO**, not an error — a deliberate cap (ticket `TASK-FIX-SPECHANG`)
that bounds the `test-orchestrator` specialist's SDK timeout to 600s to prevent
hangs. It fired as designed; every specialist run finished well within the cap.

### Lessons
- No action. Documented here only so the `capped from … to …` wording isn't
  mistaken for a truncation/failure on future log reads.

---

## Error 5 — `complete` / `worktree cleanup` are placeholders in this CLI version

### Symptom
- `guardkit autobuild complete FEAT-MEM-03` (and `--dry-run`) only printed a
  "READY FOR MERGE" handoff panel; it did **not** merge, archive, move task
  files, or clean up the worktree.
- `guardkit worktree cleanup FEAT-MEM-03` → `Unknown command: worktree`.
- `git worktree remove .guardkit/worktrees/FEAT-MEM-03` first failed with
  `contains modified or untracked files, use --force to delete it` — the worktree
  held the bootstrap `.venv` plus a leftover
  `.guardkit/autobuild/TASK-DW-005/checkpoints.json`.

### Resolution
Finalized by hand (branch was fully merged; only the venv/process artifacts were
untracked):
```bash
git merge --no-ff autobuild/FEAT-MEM-03 -m "Merge autobuild/FEAT-MEM-03: …"
git worktree remove --force .guardkit/worktrees/FEAT-MEM-03
git worktree prune
git branch -d autobuild/FEAT-MEM-03
```
Then replicated the FEAT-MEM-02 finalize convention manually: marked the feature
YAML `completed`, archived `events.jsonl` + `review-summary.md`, **moved**
`TASK-DW-001..005` from `tasks/design_approved/` → `tasks/completed/`
(`status: completed`), and archived the reference docs to
`tasks/completed/deterministic-writer/`.

### Lessons
- Same as FEAT-MEM-05: in this CLI version treat `/feature-complete` as
  "verify + print instructions", and do the git merge, `git worktree remove
  --force`, and `git branch -d` by hand.
- The worktree will always be "dirty" with its own `.venv` and trailing
  checkpoint JSON, so `git worktree remove` needs `--force` — confirm the branch
  is fully merged (`git log <branch> --not main` is empty) before forcing.
- The CLI's task-move-to-`completed` step is a placeholder. Unlike FEAT-MEM-05
  (which left duplicate `.md` files in `design_approved`), this run reconciled
  them with a real `git mv` so no stale duplicates remain.

---

## What went right (worth keeping)

- **5/5 first-turn approvals, 0 ceiling hits, 0 stalls** — the task decomposition
  from `/feature-plan` (1 helper task → core → 2 parallel + supersession → tests)
  was well-sized; each task fit comfortably inside one Player/Coach turn.
- **Smoke gate after Wave 3** (`pytest tests/unit -x`) passed, catching nothing
  because nothing was broken — exactly the desired outcome.
- **Clean merge** — the feature branch touched none of `main`'s pre-existing dirty
  paths (`.guardkit/graphiti-query-log.jsonl`,
  `features/deterministic-writer/deterministic-writer.feature`), so `git merge
  --no-ff` applied without the conflict that blocked FEAT-MEM-05.

---

## Verification performed

- `main`, post-merge writer unit suites
  (`test_writer_core`, `test_writer_identity`, `test_writer_idempotency`,
  `test_writer_supersession`, `test_supersession`): **73/73 passed**.
- Branch confirmed fully merged before deletion (`git log
  autobuild/FEAT-MEM-03 --not main` empty).

## Deliverables landed on `main`

4 writer modules — `identity.py`, `core.py`, `supersession.py`, `__init__.py`
(under `src/fleet_memory/writer/`) — plus 5 unit and 2 integration test suites.
Merge commit `c6c6983`, finalize commit `201f09d`. Not yet pushed to origin.
