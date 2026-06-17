# Retro: FEAT-MEM-04 (Relay Integration) AutoBuild

**Date:** 2026-06-13
**Feature:** FEAT-MEM-04 — Relay Integration (durable FastStream consumer on the MEMORY stream)
**AutoBuild result (as reported):** 7/7 tasks, status `completed`, all Coach-approved
**Actual result after independent verification:** 1 regression found and fixed; merged to `main` green (273/273 unit tests)

---

## Summary

The autonomous Player–Coach build reported a clean **7/7 SUCCESS** across 4 waves. Independent
verification (running the full unit suite in the worktree venv) caught **one real regression that the
Coach had approved**. It was a one-line dependency-injection wiring bug introduced in the final wave.
After fixing it, the feature merged to `main` fast-forward with the full suite green.

This retro documents the errors observed during the run, their root causes, and the process gaps that
let the regression through.

---

## Errors observed

### 1. Coach false-approval — regression slipped through (primary issue)

**Severity:** High (a green build hid a real failure)

**What happened.** Wave 4 (`TASK-RLY-006`, the thin MEMORY-stream handler + app wiring) wired
`RelayService` into the `app.py` lifespan, constructing its writer dependency as:

```python
deterministic_writer = DeterministicWriter(store=store)   # ❌ missing required `settings`
```

`DeterministicWriter.__init__(self, store, settings)` requires `settings`. The call broke the
pre-existing test `tests/unit/test_app_lifespan.py::test_lifespan_enters_and_exits_cleanly_with_fake_store`
with:

```
TypeError: DeterministicWriter.__init__() missing 1 required positional argument: 'settings'
```

**Why the Coach approved it.** The Player verified only the *new* relay module tests, not the full
suite, so the regression in a *pre-existing* test (`test_app_lifespan.py`) was never exercised during
the turn. The Coach approved against the in-scope ACs.

**Why the smoke gate missed it.** The feature's smoke gate (`pytest tests/unit -x`) is configured to
run **after wave 3** — *before* wave 4 introduced the `app.py` change. So the gate ran against a tree
that did not yet contain the bug.

**The fix.**

```python
deterministic_writer = DeterministicWriter(store=store, settings=settings)
```

Result: 1 failed / 272 passed → **273 passed** after the fix.

**Root cause classification:** verification scope. Per-task Coach verification is necessary but not
sufficient; the wave that wires components into a shared entrypoint (`app.py` lifespan / DI) is exactly
where a narrow test scope + an early-positioned smoke gate leave a blind spot.

---

### 2. `TASK-RLY-007` auto-deferred (expected, not a defect)

`TASK-RLY-007` (verify relay ack/nak/DLQ contract D5/D9) was skipped at dispatch with
`status: deferred` — `operator follow-up — runtime verification required`. Its acceptance criteria need
a live NATS/JetStream broker, which AutoBuild cannot exercise in a worktree. No Player/Coach invocation,
no SDK budget burned.

**Action required:** manual runtime verification, then `/task-complete TASK-RLY-007`. Still open as of
this retro.

---

### 3. Benign Graphiti / FalkorDB teardown traceback (noise, not a failure)

After the feature reported `status=completed`, the log emitted a
`FalkorDB ... RuntimeError: no running event loop` traceback from `edge_fulltext_search` during
post-orchestration teardown. This is known teardown noise — it occurs *after* orchestration finishes and
does not affect the build outcome.

---

### 4. Merge-time friction (during `/feature-complete`)

Not an AutoBuild defect, but recorded for process completeness:

- **CLI archival/cleanup are placeholders.** `guardkit autobuild complete` Phase 2 (task completion) and
  Phase 3 (archival + worktree cleanup) are placeholders in this version. The git merge,
  `git worktree remove`, and `git branch -d` had to be done by hand.
- **Working-tree tracking churn blocked the FF merge.** The primary repo had uncommitted autobuild
  bookkeeping (YAML re-indentation of the `tasks/backlog/relay-integration/*.md` files, feature-YAML
  status updates) that collided with the fast-forward. Resolved by `git stash` → `git merge --ff-only`
  → `git stash pop`, then discarding the non-semantic reformatting churn while preserving genuinely
  unrelated edits (`features/retrieval-api/…`, `graphiti-query-log.jsonl`). One stash-pop conflict on a
  task `.md` moved `backlog/ → design_approved/` was resolved by taking the merged (branch-authoritative)
  version.

---

## What went well

- Player–Coach loop was efficient: 5/7 first-turn approvals, `TASK-RLY-006` self-recovered a test
  failure in 2 turns, 0 SDK ceiling hits.
- Substantial, well-tested output: 6 relay modules + 6 test files (~2050 test lines), all relay tests
  passing.
- Infrastructure healthy throughout (venv bootstrap, FalkorDB, embed service).

---

## Action items / lessons

1. **Always run the FULL unit suite in the worktree venv before `/feature-complete`** — not just the
   per-task or per-module tests. A green Coach is necessary but not sufficient.
   ```bash
   .guardkit/worktrees/<FEAT>/.venv/bin/python -m pytest tests/unit -q
   ```
2. **Pay special attention to the wave that wires components into shared entrypoints** (`app.py`
   lifespan, DI, broker context). That is the highest-risk spot for cross-module regressions that
   narrow per-task verification misses.
3. **Smoke-gate placement matters.** A gate positioned after wave 3 cannot catch wave-4 edits. Consider a
   final full-suite gate after the *last* wave, or scope per-task verification to the full suite for
   wiring tasks.
4. **Expect to finalize by hand.** Treat `guardkit autobuild complete` archival/cleanup as not-yet-
   implemented; do the merge, worktree removal, and branch deletion manually.
5. **Don't forget the deferred operator task** (`TASK-RLY-007`) — it needs live-broker verification.

> Cross-reference: the false-approval pattern (and the broader catalogue of AutoBuild failure modes on
> this machine) is captured in the persistent memory `guardkit-autobuild-quirks` (item 5).
