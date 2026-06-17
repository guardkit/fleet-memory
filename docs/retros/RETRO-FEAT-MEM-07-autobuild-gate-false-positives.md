# RETRO — FEAT-MEM-07 AutoBuild gate false-positives

**Date:** 2026-06-16
**Feature:** FEAT-MEM-07 — Re-index Pipeline (11 tasks, RIP-001…RIP-011)
**Outcome:** Merged to `main` (`373dc97`). 10 tasks completed, RIP-011 deferred (operator handoff). Full unit suite green on main (468 passed).
**Purpose:** Record the AutoBuild errors hit during the run, their root causes, the fixes, and the prevention so the next feature doesn't re-pay this cost.
**Related:** [phase-core-build-plan.md §FEAT-MEM-07](../research/ideas/phase-core-build-plan.md); the canonical bridge template lives in `guardkit/installer/core/templates/common/features/conftest.py.template`.

---

## TL;DR

Every task that "failed" during the build was a **harness gate false-positive, not a code defect** — ground-truthed each time by running the real suite in the worktree venv (468 unit tests green throughout). Three distinct gate bugs plus one self-inflicted destructive-flag mistake cost the run. The actual implementation was sound from wave 1; the loop just couldn't *see* that through the gates.

| # | Symptom | Real cause | Class |
|---|---------|-----------|-------|
| 1 | Every task's BDD oracle reports a synthetic failure | No `features/conftest.py` collection bridge → `pytest <file>.feature` exits 4 | Missing infra (repo-wide) |
| 2 | RIP-002 `UNRECOVERABLE_STALL` | plan_audit read a markdown-link **label** as a file path | Scanner false-positive |
| 3 | RIP-007 `UNRECOVERABLE_STALL` (pollution) | honesty gate flagged an orchestrator file + pollution guard early-exit | Gate false-positive |
| 4 | RIP-001 work + fix commit wiped mid-run | `--fresh` hard-resets the worktree to base | Operator/flag misuse |

---

## Error 1 — BDD gate exit-4 (affects every task in every feature)

**Symptom**
```
BDD runner for TASK-RIP-002: pytest exited with 4 and produced no testcases;
surfacing as synthetic failure.
ERROR: not found: .../features/re-index-pipeline/re-index-pipeline.feature
BDD runner for TASK-RIP-002: passed=0 failed=1 pending=0
```

**Root cause**
`bdd_runner` invokes `pytest --gherkin-terminal-reporter --junitxml=… -m <task_tag> features/<slug>/<slug>.feature`. pytest-bdd v8 does **not** register a `pytest_collect_file` hook for `.feature` files, so pytest can't collect a literal `.feature` path and exits 4 ("not found"), which the runner surfaces as a synthetic BDD failure for **every** task. The repo's existing `tests/bdd/test_*.py` bindings are in the wrong place — the bridge resolves glue as a **sibling** of the `.feature` file, not under `tests/`.

**Fix**
- Installed the canonical bridge `guardkit/installer/core/templates/common/features/conftest.py.template` → `features/conftest.py`.
- Added sibling glue `features/re-index-pipeline/test_re_index_pipeline.py` calling `pytest_bdd.scenarios("re-index-pipeline.feature")`.
- Unimplemented steps raise `StepDefinitionNotFoundError`, which the runner classifies as **pending** (tolerated; the gate passes when `scenarios_failed == 0`). Verified end-to-end: RIP-002's scenario went `passed=0 failed=0 pending=1`.

**Note:** this was masked on RIP-001 and on prior features — a synthetic BDD failure alone doesn't block; it only becomes fatal when combined with another gate failure (Errors 2/3). It had been quietly failing for the whole repo.

---

## Error 2 — plan_audit AC-scanner reads link labels as file paths (RIP-002)

**Symptom**
```
plan_audit: status=violation, severity=high
  missing_files: ["relay/service.py"]
  message: "no plan on disk; AC names file path(s) that do not exist on disk: relay/service.py"
→ all_gates_passed=False → criteria short-circuit (0 verified, 7 rejected) → UNRECOVERABLE_STALL
```

**Root cause**
`agent_invoker._scan_ac_for_missing_paths` regex-extracts path-shaped tokens from the `## Acceptance Criteria` section and flags any multi-segment token (contains `/`) where `(worktree / token).exists()` is false. The AC carried a markdown link `[relay/service.py](src/fleet_memory/relay/service.py)`. The scanner extracted the **label** `relay/service.py` (not a repo-root path) and flagged it — even though the **href** `src/fleet_memory/relay/service.py` exists. Bare basenames (no `/`, e.g. `settings.py`) are deliberately skipped, which is why RIP-001's `[settings.py](…)` passed and RIP-002's didn't.

**Fix**
Normalized AC link/backtick path labels across the RIP task files to their real `src/fleet_memory/…` paths (so the extracted token resolves). Left task-output files that legitimately don't exist yet (correct full paths under `reindex/`/`tests/`) untouched — they exist by Coach time.

---

## Error 3 — honesty gate + pollution guard (RIP-007)

**Symptom**
```
gather_evidence: honesty produced N must_fix issue(s) for TASK-RIP-007; downstream skipped.
  claim_audit (critical): Player claimed file coverage.json. Actual: Path absent from 'git status --porcelain'
Unrecoverable stall detected for TASK-RIP-007: context pollution detected but no passing checkpoint exists.
```

**Root cause**
RIP-007's code was complete and correct — its own `phase_4_summary` recorded **567 passed, 0 failed, 91% coverage, quality_gates_passed=true**. The stall came from two things stacking:
1. The honesty `claim_audit` gate flagged orchestrator-managed artifacts the Player listed in `files_modified` (`coverage.json`, `.claude/task-plans/*`, pytest node-IDs like `test_x.py::test_y`). One escalated to `must_fix`/critical and short-circuited evidence gathering.
2. `rollback_on_pollution=True` saw the per-turn test status regress (turn 1 pass → turns 2-3 fail) and exited early ("no passing checkpoint") before the loop could self-correct.

**Fix**
A clean re-run via `--resume` — RIP-007 approved on **turn 1** with no pollution stall. (Same recovery pattern as RIP-002, which also threw honesty `must_fix` on turn 1 of its clean re-run and recovered to approved by turn 3.) The honesty-report hygiene issue is non-deterministic Player behaviour; the fix that mattered was *not permanently short-circuiting on it*, which Errors 1 & 2 had been causing.

---

## Error 4 — `--fresh` destroyed approved work (self-inflicted)

**Symptom**
After `guardkit autobuild feature FEAT-MEM-07 --task TASK-RIP-002 --fresh`, RIP-001's approved `walker.py` and the BDD/plan_audit fix commit were both gone; the BDD gate exit-4'd again because `features/conftest.py` had vanished.

**Root cause**
`--fresh` is not "retry this task." When state is incomplete it runs `_clean_state` and **recreates the worktree from the base branch**, hard-resetting to base and discarding every checkpoint commit **and any manual commits** on the worktree branch (the fixes were committed in the worktree, not the base).

**Fix / recovery**
- The orphaned fix commit was still a reachable git object → `git reset --hard <sha>` in the worktree restored RIP-001 work + RIP-002 code + the fixes.
- Re-ran with `--resume` instead, which **reuses the existing worktree as-is** (only `--refresh` rebases; only `--fresh` recreates). Guarded every relaunch by checking `walker.py`/`audit.py` survived before letting it proceed.

---

## What went right

- **Ground-truthing beat the gate verdicts every time.** Running `pytest tests/unit` in the worktree venv (468 green) on each "failure" is what revealed all four were false-positives. Never trusted a `FAILED`/`UNRECOVERABLE_STALL` at face value.
- Reading the guardkit source (`bdd_runner.py`, `coach_validator.py`, `agent_invoker._scan_ac_for_missing_paths`, `feature_orchestrator`) pinned each root cause precisely rather than guessing.
- `--resume` reliably reused the worktree; clean re-runs recovered the honesty/pollution stalls without code changes.

## Prevention / follow-ups

1. **Keep `features/conftest.py` in `main`** — it fixes BDD exit-4 for *every* feature, not just this one. (Merged with FEAT-MEM-07.) Consider also moving feature glue to the sibling `features/<slug>/test_<slug>.py` location the bridge expects.
2. **Never use `--fresh` to retry.** Use `--resume`. Reserve `--fresh` for a genuine from-scratch rebuild *with fixes already on the base branch*.
3. **Author AC file references as bare paths or matching label==href.** `[relay/service.py](src/fleet_memory/relay/service.py)` trips plan_audit; write ``src/fleet_memory/relay/service.py`` or `[src/fleet_memory/relay/service.py](src/fleet_memory/relay/service.py)`.
4. **Upstream candidates for guardkit** (would remove the false-positives at the source):
   - plan_audit: extract markdown-link **hrefs**, not labels; resolve multi-segment tokens as path suffixes before declaring "missing."
   - honesty `claim_audit`: exclude orchestrator-managed paths (`coverage*.json`, `.claude/task-plans/*`, `.guardkit/**`) and pytest node-IDs from the Player's file claims (the ghost-path filter already exists; widen it).
   - pollution guard: don't early-exit when a passing checkpoint exists earlier in the run.
5. **56 BDD scenarios remain pending** (unbound step definitions) — tolerated as scaffolding, 78 pass, zero real failures. Binding them is separate, optional work.
6. **RIP-011 operator follow-up** is still owed (full live corpus re-index timing/no-LLM/idempotency/audit/parity verification, then `/task-complete TASK-RIP-011`).
