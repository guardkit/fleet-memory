# AutoBuild Retro — FEAT-MEM-02 (Typed Payload Registry)

**Date:** 2026-06-16
**Run:** `guardkit autobuild feature FEAT-MEM-02` → `/feature-complete FEAT-MEM-02`
**Outcome:** SUCCESS — 4/4 tasks coach-approved (1 turn each), merged to `main` (`3655188`), `188 passed, 32 deselected` on merged main.

This retro documents the **errors, warnings, and tooling gaps** observed during the run. None blocked completion, but several added latency, produced misleading signals, or required manual intervention during merge/cleanup. The Player-generated code itself was sound — every issue below is in the harness, infra, or convention layer, not the implementation (consistent with "ground-truth tests before blaming Player code").

---

## Summary table

| # | Issue | Severity | Layer | Blocking? |
|---|-------|----------|-------|-----------|
| 1 | Graphiti context loads wildly slow / timed out (0.7s–1859s) | High | Infra (Graphiti) | No (dominated wall-clock) |
| 2 | BDD runner path mismatch → synthetic test failures | Medium | Harness (BDD runner) | No (misleading signal) |
| 3 | `guardkit autobuild complete` does not merge/archive (placeholders) | Medium | CLI | Yes (manual merge required) |
| 4 | `guardkit worktree cleanup` — unknown command | Low | CLI | Yes (manual cleanup) |
| 5 | `.guardkit/worktrees/FEAT-MEM-02` tracked as git gitlink | Low | Repo state | No (manual fix) |
| 6 | `tree_sitter_language_pack` missing → wiring analysis disabled | Low | Deps | No |
| 7 | FalkorDB workaround skipped (decorator source changed) | Low | Infra | No |
| 8 | Python 3.14 / Pydantic v1 incompatibility warning | Low | Runtime | No |

---

## 1. Graphiti context loads — extreme, variable latency

The single largest cost of the ~90-minute run. Per-turn context retrieval times observed:

| Turn / phase | Load time |
|---|---|
| TASK-TPR-001 Player | 0.9s |
| TASK-TPR-002 Player | 0.7s |
| TASK-TPR-002 Coach | 19.1s |
| TASK-TPR-003 Player | 11.8s |
| TASK-TPR-003 Coach | 147.5s |
| TASK-TPR-004 Player | **1859.2s (~31 min)** |
| (mid-run) | 193.7s |
| TASK-TPR-004 Coach | 371.0s |

Also surfaced:
```
WARNING:guardkit.knowledge.graphiti_client:Search request failed: Request timed out.
```

**Impact:** Context retrieval (not implementation) dominated wall-clock. The advertised "~600–800ms per turn" budget was exceeded by 3–4 orders of magnitude on several turns. The payload returned was tiny (~350 chars) regardless of load time, so the latency bought almost no context.

**Recommendation:** Add a hard per-call timeout + fallback-to-empty-context on the Graphiti client (it already times out internally but still blocked ~31 min on one call). Investigate the embedding endpoint (`promaxgb10-41b1:9000`) / FalkorDB query latency. Consider caching or making context load fully async/non-blocking with a short ceiling.

---

## 2. BDD runner path mismatch → synthetic failures

For TASK-TPR-001, -002, and -003 the BDD quality gate reported a failure:
```
WARNING:...bdd_runner:BDD runner for TASK-TPR-001: pytest exited with 4 and produced no
testcases; surfacing as synthetic failure. ... 'ERROR: not found:
.../features/typed-payload-registry/typed-payload-registry.feature (no match ...)'
INFO:...bdd_runner:BDD runner for TASK-TPR-001: passed=0 failed=1 pending=0
```

The runner looked for `features/typed-payload-registry/typed-payload-registry.feature`, but the Player implemented BDD as pytest-bdd suites under `tests/bdd/test_typed_payload_registry.py`. The expected `.feature` file never existed at that path, so the runner manufactured a `failed=1` result.

**Impact:** This is the source of the misleading **"1 tests (failing)"** line in the Player turn summaries. It did **not** block approval (waves passed, coach approved), but it required manual ground-truthing (`pytest tests/ -m "not integration"` → 188 passed) to confirm the suite was actually green.

**Recommendation:** Align the BDD runner's expected feature-file path with where `/feature-plan`/Player actually generate BDD artifacts, or detect "no matching .feature" as *not-applicable* rather than a synthetic failure. A non-existent gate input should be neutral, not a failure.

---

## 3. `guardkit autobuild complete` is a no-op merge

`guardkit autobuild complete FEAT-MEM-02` ran "successfully" but its Phase 2 (Task Completion) and Phase 3 (Archival) are unimplemented placeholders:
```
Phase 2: Task Completion
  → Placeholder for TASK-FC-002
  → Will mark incomplete tasks as complete
Phase 3: Archival
  → Placeholder for TASK-FC-003
  → Will archive feature YAML / cleanup worktree
```
It only printed a "READY FOR MERGE" handoff panel — it did **not** merge, archive, move task files, or clean up.

**Impact:** The documented `/feature-complete` flow (auto-merge, archive, status updates, worktree cleanup) did not happen. The merge, branch deletion, status updates, task-file moves, and worktree removal were all performed manually.

**Recommendation:** Either implement TASK-FC-002/003 or update the `/feature-complete` slash-command docs to state that the installed CLI only hands off, so operators expect to merge manually.

---

## 4. `guardkit worktree cleanup` — unknown command

The handoff panel (and `/feature-complete` docs) instruct:
```
guardkit worktree cleanup FEAT-MEM-02
```
But:
```
Unknown command: worktree
Run 'guardkit help' for usage information
```

**Impact:** Cleanup fell back to raw git (`git worktree remove --force` + `git worktree prune` + `git branch -D`).

**Recommendation:** Add the `worktree` subcommand or correct the docs/handoff text to the git commands.

---

## 5. Worktree directory tracked as a git gitlink

`.guardkit/worktrees/FEAT-MEM-02` was a tracked entry in the repo (appeared in `git ls-files` and showed as `M`, then `D` after removal). Worktree directories should never be committed.

**Impact:** Removing the worktree left a staged deletion that had to be committed as bookkeeping. Risk of future confusion / accidental re-commit.

**Recommendation:** Add `.guardkit/worktrees/` to `.gitignore` and `git rm --cached` any tracked worktree paths.

---

## 6. `tree_sitter_language_pack` missing — wiring analysis disabled

Repeated (~13×) during specialist analysis:
```
WARNING:guardkitfactory.wiring.parser:Parse failed for language 'python':
tree_sitter_language_pack is required for wiring analysis.
Install it with: pip install tree-sitter-language-pack
```

**Impact:** Wiring/dependency analysis silently degraded. Did not affect this feature's outcome but reduces review depth.

**Recommendation:** Add `tree-sitter-language-pack` to the autobuild extras, or downgrade the message and confirm graceful degradation is intended.

---

## 7. FalkorDB workaround skipped

```
WARNING:...falkordb_workaround:[Graphiti] FalkorDB decorator source changed unexpectedly,
skipping workaround (manual review needed)
```

**Impact:** A compatibility shim no longer matched the upstream decorator and was skipped. Possibly related to the Graphiti latency in #1.

**Recommendation:** Review the FalkorDB decorator monkeypatch against the installed version; pin the dependency or update the workaround.

---

## 8. Python 3.14 / Pydantic v1 incompatibility warning

Emitted on every CLI invocation:
```
UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.
```

**Impact:** Noise only in this run, but a latent risk — a transitive dep still imports `pydantic.v1` under Python 3.14.

**Recommendation:** Track the offending dependency (langchain_core) and pin/upgrade, or run autobuild under a supported interpreter.

---

## What went well

- All 4 tasks approved in a single turn each; 0 SDK turn-ceiling hits; clean executions 4/4.
- Player-generated code was correct and fully tested (188 unit/integration-excluded tests pass on merged main).
- The "synthetic BDD failure" did **not** corrupt the real test suite — ground-truthing confirmed green.
- Manual merge was clean (no real conflicts; the apparent two-dot "deletions" were just untracked-in-main planning files absent from the branch).

## Key takeaway

The implementation layer was reliable; **the friction was entirely in infra (Graphiti latency), harness conventions (BDD path), and CLI completeness (merge/cleanup placeholders).** Prioritise #1 (Graphiti timeout/fallback) and #2 (BDD path/neutral-on-missing) — together they account for the wasted wall-clock and the only misleading quality signal in the run.
