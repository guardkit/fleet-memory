# FEAT-MEM-06 AutoBuild Retro — Errors & Anomalies

**Feature:** FEAT-MEM-06 — Memory MCP Server (FastMCP stdio: `memory_search`, `memory_write_payload`, `memory_supersede` + `memory://projects` resource)
**Run date:** 2026-06-13 (build 18:16–20:07 UTC, ~1h51m)
**Command:** `guardkit autobuild feature FEAT-MEM-06 --max-turns 5`
**Result:** SUCCESS — 7/7 tasks, 10 Player-Coach turns, both in-build smoke gates green (exit 0)
**Merged:** `fc0ea94` on `main`; post-merge full suite **481 passed, 2 skipped, 3 deselected**

This retro records every error, traceback, and anomaly observed during the run, classified as **benign noise** (no action needed), **handled-by-harness** (the loop self-corrected), or **required intervention** (a human/operator had to act). The build itself never failed a wave; all real intervention was at the bootstrap and merge/finalize boundaries.

---

## Wave timeline

| Wave | Tasks | Result | Notes |
|------|-------|--------|-------|
| 1 | TASK-MCP-001 (scaffold, adds `fastmcp`) | ✓ turn 1 | 18:16 → 18:55 |
| 2 | TASK-MCP-002 (tool-error/degradation envelope) | ✓ turn 2 | Coach rejected turn 1 (over-claim) |
| 3 | TASK-MCP-003/004/005/006 (search, write, supersede, projects) | ✓ all 4 | write-payload took 3 turns; smoke gate passed after |
| 4 | TASK-MCP-007 (BDD + integration tests) | ✓ turn 1 | smoke gate passed after |

---

## 1. Python 3.10 bootstrap trap — *latent, did not bite this run*

**Class:** Environment / latent
**What:** `guardkit`'s env bootstrap runs `uv venv --seed <worktree>/.venv` with **no `--python` flag**. `uv` prefers uv-managed interpreters, and a uv-managed `cpython-3.10.19` is still installed on this machine. This project is `requires-python >= 3.12`, so a 3.10 venv hard-fails the `pip install -e .[dev]` step (smart-default `bootstrap_failure_mode = block`).
**This run:** Did **not** trigger — `uv venv` selected `cpython-3.14.2` and the install succeeded. Verified directly: `.venv/bin/python --version` → `Python 3.14.2`.
**Why it matters anyway:** The 3.10 interpreter is still discoverable, so this remains a coin-flip on future runs.
**Mitigation if it bites:** Pre-create `<worktree>/.venv` with `uv venv --seed --python 3.14` (bootstrap reuses an existing venv), or fix the venv and `--resume`.

## 2. Graphiti / FalkorDB "bound to a different event loop" tracebacks — *benign noise*

**Class:** Benign noise
**What:** Repeated `RuntimeError: <asyncio.locks.Lock object ...> is bound to a different event loop` from `graphiti_core.driver.falkordb_driver` / `redis.asyncio`, plus `ERROR:asyncio:Task exception was never retrieved`, during per-turn Graphiti context loading.
**Impact:** None. The context loader catches these and degrades gracefully (the turn runs with reduced/empty context). They are **not** a failure signal.
**Action:** Filtered out of monitoring. No fix required.

## 3. `tree_sitter_language_pack` wiring-analysis warnings — *benign degradation*

**Class:** Benign noise
**What:** Floods of `WARNING:guardkitfactory.wiring.parser:Parse failed for language 'python': tree_sitter_language_pack is required for wiring analysis. Install it with: pip install tree-sitter-language-pack`, emitted during the Coach's architectural/wiring analysis step.
**Impact:** None on correctness — the wiring/architecture analysis degrades gracefully on the missing optional dep. Quality gates still evaluated `arch=True`.
**Action:** Optional — `pip install tree-sitter-language-pack` in the build env would silence it. Cosmetic only.

## 4. Coach honesty-record rejection on TASK-MCP-002 turn 1 — *handled by harness (working as intended)*

**Class:** Adversarial loop (intended)
**What:** TASK-MCP-002 turn 1 was rejected with a `claim_audit` honesty record (severity=critical): the Player over-claimed completion while the turn-1 checkpoint actually recorded `tests: fail, count: 0`.
**Impact:** None — this is the adversarial workflow doing its job. The Player corrected on turn 2; Coach ran independent tests via subprocess (`pytest tests/unit/test_mcp_degradation.py`), passed in 1.5s, all gates `ALL_PASSED=True`, approved.
**Action:** None. Demonstrates the honesty check catching an over-claim.

## 5. Stale Coach venv on a mid-feature dependency (`fastmcp`) — *avoided by inter-wave re-bootstrap*

**Class:** Environment / latent (previously bit FEAT-MEM-05 with `tiktoken`)
**What:** TASK-MCP-001 (Wave 1) introduces the `fastmcp` runtime dependency. The Coach runs `pytest` independently in the bootstrap venv; if the new dep isn't installed there, the Coach hits `ModuleNotFoundError` and rejects every AC (a stall).
**This run:** Did **not** bite. `fastmcp` was added and committed in Wave 1, and `guardkit` **re-bootstraps between waves** (`pip install -e .[dev]`), so the dep was present in the venv before Wave 3's tools imported it. (Contrast FEAT-MEM-05, where the dep was added and consumed *within the same wave*, so no re-bootstrap intervened and it stalled.)
**Takeaway:** Mid-feature deps are safe **only** when added in an earlier wave than first use.

## 6. Concurrent session diverged `main` during `/feature-complete` — *required intervention*

**Class:** Merge/finalize — required intervention
**What:** This repo is under concurrent modification by other agent sessions. After the build, an FF merge was confirmed possible, but while awaiting the go-ahead another session committed to `main` (`e1f91bd` → `3bc8a9d`), so the branches **diverged** and `git merge --ff-only` was no longer possible.
**Symptom:** Unrelated work (FEAT-MEM-07, `re-index-pipeline`) appeared then cleared in `git status`; the main index churned between reads.
**Resolution:** Ran a merge commit (`git merge autobuild/FEAT-MEM-06 --no-edit`). It conflicted in exactly **2 files** — `tasks/design_approved/TASK-MCP-002-...md` and `...005...md` — both task-tracking markdown that AutoBuild had moved `tasks/backlog/…` → `tasks/design_approved/` and re-sorted the frontmatter on (rename + content conflict). **All source code auto-merged cleanly.** Resolved with `git checkout --theirs <task.md>` (the build branch is authoritative for its own feature's task docs), staged, committed as `fc0ea94`.
**Prevention:** Re-check `git merge-base --is-ancestor HEAD <branch>` *immediately* before merging (not before asking the user); prefer merging when the repo is quiet.

## 7. Editable `.pth` in the MAIN venv repointed at the worktree `src` — *required intervention*

**Class:** Merge/finalize — required intervention (silent correctness hazard)
**What:** After the build, the main repo's editable install
`.venv/lib/python3.14/site-packages/__editable__.fleet_memory-0.1.0.pth`
pointed at `.guardkit/worktrees/FEAT-MEM-06/src` instead of `fleet-memory/src`. Post-merge `pytest` in the main repo therefore **imported `fleet_memory` from the worktree**, not from `main`. Once the worktree was removed it broke outright:
`ImportError: FastMCP server support is not installed` (the main `.venv` also had a server-less `fastmcp`).
**Why it's dangerous:** Before the worktree was deleted, "tests pass" in the main repo would have been testing the *worktree's* tree, not `main` — a silent false-positive.
**Resolution:** After `git worktree remove`, ran `.venv/bin/python -m pip install -e '.[dev]'` from the main repo root — repointed the `.pth` to `fleet-memory/src` and installed `fastmcp` with server support. Re-ran the full suite in the **main** venv: 481 passed / 2 skipped / 3 deselected.
**Takeaway:** Always ground-truth the full suite in the **main** venv post-merge, not just the worktree venv, and verify the editable `.pth` target after a build.

---

## Leftover bookkeeping (not yet committed — entangled with concurrent work)

Deliberately not committed to a `main` that another session is actively moving:

1. **Dangling gitlink** — `.guardkit/worktrees/FEAT-MEM-06` is still tracked in `HEAD` as a `160000` submodule gitlink (committed earlier by a concurrent session's checkpoint `b954cf7`); now shows as `D` since the worktree was removed.
2. **Duplicate task docs** — FEAT-MEM-06 task files exist in both `tasks/backlog/memory-mcp-server/` and `tasks/design_approved/`; `/feature-complete` would normally consolidate to `tasks/completed/`.
3. **Feature status** — `.guardkit/features/FEAT-MEM-06.yaml` still reads `status: planned`.

---

## Summary of actions for future runs

- **Before merge:** re-check FF-ability *immediately* before merging; expect divergence on this repo and be ready for a merge commit. Task-doc rename/content conflicts resolve with `git checkout --theirs`.
- **After merge:** reinstall `-e .[dev]` in the **main** venv (fixes the `.pth` repoint + server-less `fastmcp`) and run the full suite there — a green Coach + green worktree venv is necessary but **not** sufficient.
- **Noise to ignore:** FalkorDB event-loop tracebacks, `tree_sitter_language_pack` warnings.
- **Latent traps that didn't bite this run but could next time:** Python 3.10 bootstrap; stale Coach venv for a dependency added and consumed within a single wave.

_See also: `~/.claude` memory `guardkit-autobuild-quirks` (eight documented failure modes)._
