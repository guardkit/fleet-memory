# RETRO — FEAT-MEM-01 AutoBuild errors

**Date:** 2026-06-16 (build ran 2026-06-12 → merged 2026-06-13)
**Feature:** FEAT-MEM-01 / **FEAT-CA81** — Storage Substrate (13 tasks, TASK-MEM-001…013, 8 waves)
**Outcome:** Merged to `main` via fast-forward (`2a8ae61`); scaffolding + coach config (`0ca7feb`). 13/13 tasks Coach-approved. Post-merge on `main`: **78 unit + 32 integration tests green**. TASK-MEM-008 (NAS deploy) deferred as operator handoff.
**Cost:** **9 orchestrator launches** before `FEATURE RESULT: SUCCESS`. Every "task failure" but one was a harness false-positive; the one real defect was a product bug the gates legitimately surfaced.
**Purpose:** Record each error, root cause, fix, and prevention so the next feature doesn't re-pay this.
**Related:** [phase-core-build-plan.md §FEAT-MEM-01](../research/ideas/phase-core-build-plan.md); memory `guardkit-autobuild-quirks`. This was the *first* Phase CORE build, so several of these were discovered here and later re-confirmed on FEAT-MEM-04/05/06/07 (see their retros).

---

## TL;DR

Eight distinct problems across nine runs. **One was a genuine product bug** (connect-timeout not bounding the pool). The rest were harness/environment issues that made sound code look broken — confirmed each time by running the real suite directly (it passed throughout). The implementation was essentially correct from the start; the loop just couldn't *see* it through bootstrap, the Coach test runner, the plan-audit scanner, a missing env var, and an honesty check.

| # | Run(s) | Symptom | Real cause | Class |
|---|--------|---------|-----------|-------|
| 1 | 1 | Bootstrap hard-fail after wave 1 | `uv venv` built the venv on Python 3.10.19 vs `requires-python >=3.12` | Environment |
| 2 | 2 | Wave 2 both tasks burn all turns, no test signal | Coach SDK test runner never executes pytest (LLM "I'll run that…") | Harness false-positive |
| 3 | 3 | TASK-MEM-006 `UNRECOVERABLE` (3 turns) | plan_audit read AC-004's grep command as one missing file path | Harness false-positive |
| 4 | 4 | TASK-MEM-009/010 fail, BDD oracle absent | my `features/` copy dragged in `.feature` needing uninstalled `pytest-bdd` | Self-inflicted + missing infra |
| 5 | 5 | Run dies at **wave-1 smoke gate**; can't reach wave 6 | a real bug: lifespan ignored `pg_connect_timeout_s` (pool retried 30s) | **Genuine product bug** + deadlock |
| 6 | 6 | TASK-MEM-010 fail (3 turns) | AC-004 ranking test SKIPPED — `FLEET_MEMORY_EMBED_URL` unset → Coach treats skip as absent oracle | Environment |
| 7 | 7 | Player turn dies silently at ~300s, exit 0 | unexplained SDK subprocess stop; masked by `tee` | Transient / unexplained |
| 8 | 8 | TASK-MEM-012 fail (3 turns) | honesty gate: files committed in earlier turn checkpoints show "no changes this turn" → evidence gathering aborts | Harness false-positive |

Throughout: benign `FalkorDB … Lock is bound to a different event loop` tracebacks from Graphiti per-turn context loading. **Not** failures — caught and degraded (turn runs with empty context).

---

## Error 1 — bootstrap venv built on Python 3.10 (run 1)

**Symptom**
```
ERROR: Package 'fleet-memory' requires a different Python: 3.10.19 not in '>=3.12'
Bootstrap hard-fail: 0/1 install(s) succeeded for essential stack(s): python.
```
Wave 1 (TASK-MEM-001) had actually passed and its smoke gate was green; the failure was the *environment bootstrap* that runs before installing `[dev]` extras.

**Root cause**
guardkit's bootstrap runs `uv venv --seed` with no `--python` flag. uv prefers a uv-managed interpreter, and the only one installed was `cpython-3.10.19`, which violates the project's `requires-python >=3.12`. The system Python 3.14 was never selected.

**Fix**
Recreated the worktree venv on the right interpreter, then let bootstrap reuse it (it reuses an existing `<worktree>/.venv`):
```
uv venv --seed --python 3.14 .guardkit/worktrees/FEAT-CA81/.venv
```
Verified `pip install -e '.[dev]'`, `import fleet_memory`, and the unit smoke before resuming. Durable fix: `uv python install 3.14` (or remove the managed 3.10) so uv stops defaulting to 3.10 in future worktrees.

---

## Error 2 — Coach SDK test runner never runs pytest (run 2)

**Symptom**
Both Wave 2 tasks (TASK-MEM-002, TASK-MEM-004) burned all their turns. Every Coach turn reported:
```
evidence_bundle.independent_tests.tests_passed = false
test_output_summary: "I'll run that test command for you and show you the full output."
```
The Coach itself flagged it as infrastructure, not code: *"This appears to be an infrastructure issue with the independent test runner, not a problem with the Player's implementation."*

**Root cause**
The default Coach independent-test path (`coach_test_execution="sdk"`) runs the pinned `pytest` command through a **one-turn LLM agent** with a Bash tool. On this machine that agent narrates *"I'll run that test command for you…"* and never invokes Bash — so the Coach gets no test signal and rejects every AC. Ground truth: the same command run directly passed 24/24.

**Fix**
guardkit has a built-in subprocess fallback (`coach_validator._run_tests_via_sdk` vs the subprocess path gated on `self._coach_test_execution`). Created `.guardkit/config.yaml`:
```yaml
autobuild:
  coach:
    test_execution: subprocess
```
Re-read on every Coach invocation (no restart). It landed mid-run though, so Wave 2 still exhausted its turns and the run exited FAILED — the *next* resume picked it up. Now committed in `0ca7feb` so it persists.

---

## Error 3 — plan_audit reads a grep command as a missing file (run 3, TASK-MEM-006)

**Symptom**
```
plan_audit: status=violation, severity=high
  missing_files: ['grep -rE "from nats|import nats|faststream" src/.../store.py src/.../embed.py src/.../settings.py']
gathering_status: 'partial_gate_abort'  → Guard 5 blocks approval → 3 turns, no recovery
```

**Root cause**
When no implementation plan is on disk, `agent_invoker._scan_ac_for_missing_paths` extracts path-shaped tokens from the AC section and flags any that don't exist. AC-004 was a single backtick span: `` `grep -rE "…" src/…/store.py src/…/embed.py src/…/settings.py` `` ending in `settings.py`. The scanner captured the **whole command** as one "file path", which of course doesn't exist → high violation → evidence gathering aborts before tests ever run → unwinnable loop. (Implementation was fine: 69 unit tests passed, service-layer boundary clean.)

**Fix**
Reworded AC-004 so the grep pattern and each of the three paths sit in **separate** backtick spans (the individual paths exist on disk). Pre-emptively ran the scanner's regex over the remaining task files; that surfaced Error 4's seed too (MEM-013 references `features/storage-substrate/storage-substrate_assumptions.yaml`, which was missing from the worktree — copied `features/` in).

---

## Error 4 — BDD oracle absent + my own `features/` copy (run 4)

**Symptom**
TASK-MEM-009 errored and TASK-MEM-010 failed; Coach reported:
```
BDD oracle: feature files exist (features/storage-substrate/storage-substrate.feature)
but pytest-bdd is not installed → 0 scenarios executed → ABSENT SIGNAL
```

**Root cause**
Self-inflicted: the `features/` directory I copied into the worktree for Error 3 included `storage-substrate.feature`, whose `@task:`-tagged scenarios made the BDD gate demand `pytest-bdd` (not a project dependency). The build interpreted "tagged feature file present + pytest-bdd missing" as an absent oracle and rejected. (This same exit-4/BDD-bridge class was later fixed properly in FEAT-MEM-07 with a `features/conftest.py` bridge.)

**Fix**
Removed `storage-substrate.feature` from the worktree (kept the assumptions YAML MEM-013 needs). Unit and integration tiers don't need pytest-bdd.

---

## Error 5 — genuine bug: lifespan ignored `pg_connect_timeout_s`, and a smoke-gate deadlock (run 5)

**This is the one real defect AutoBuild's tests legitimately caught.**

**Symptom**
The `test_startup_failure_with_unreachable_database` unit test failed: startup against a closed port took **30s, expected < 15s**. Worse, this made `pytest tests/unit` exit 1, so the **wave-1 smoke gate** (which fires after every wave) failed — and the run could never advance to Wave 6 where the failing test lived. Deadlock: a failing test the loop structurally couldn't reach to fix.

**Root cause**
`async_store_context` passed `connect_timeout` as a per-connection kwarg, but that does **not** bound psycopg-pool's own open/retry loop (default 30s). So an unreachable database stalled lifespan entry to 30s regardless of `pg_connect_timeout_s` — exactly the ASSUM-006 risk the spec called out. An integration test had even *codified the broken behaviour* (asserting 25–35s elapsed) as an "observation".

**Fix** (committed `b644f02`)
Bounded context entry (pool open + `setup()`) with `asyncio.timeout(pg_connect_timeout_s + 5s slack)`, raising a credential-free `TimeoutError` that names host:port. Rewrote `test_connection_timeout_behavior` to assert the bounded fast-fail. Fixing the real bug cleared the smoke-gate deadlock at the same time.

---

## Error 6 — real-embed ranking test skipped → "absent oracle" (run 6, TASK-MEM-010)

**Symptom**
```
AC-004 test 'test_semantic_search_ranking_with_real_embeddings' was SKIPPED, not executed.
The test skips when FLEET_MEMORY_EMBED_URL is not set. A skipped test is an absent oracle.
```

**Root cause**
The ranking test needs real nomic embeddings and `pytest.skip`s when `FLEET_MEMORY_EMBED_URL` is unset. The Coach treats a skipped AC test as an absent oracle and rejects — correctly, in principle. The orchestrator simply wasn't given the env var.

**Fix**
Verified the test passes against the live llama-swap service (`http://promaxgb10-41b1:9000`, serves `nomic-embed`) — 7s, green. Relaunched the orchestrator with `FLEET_MEMORY_EMBED_URL` exported so Player and Coach test runs inherit it. (Now recorded in memory `fleet-memory-test-environment`.)

---

## Error 7 — Player turn dies silently at ~300s, exit 0 (run 7)

**Symptom**
Run 7's TASK-MEM-010 Player turn logged `…in progress… (300s elapsed)` and then the process simply ended — exit code 0, no error, no traceback. Masked because the launch piped through `tee`, which reported the pipe's success rather than the orchestrator's status.

**Root cause**
Never definitively root-caused — an apparent SDK subprocess stop with no diagnostic. Possibly transient (API/transport). Did not recur.

**Fix / mitigation**
Relaunched with `>> logfile 2>&1; echo "EXIT_CODE=$?"` instead of `tee`, so the orchestrator's real exit code is visible. Run 8's resume completed TASK-MEM-010 in **1 turn** — the code was fine; the prior turn just died mid-flight.

---

## Error 8 — honesty gate: "files show no changes this turn" (run 8, TASK-MEM-012)

**Symptom**
```
partial_honesty_abort — Player claimed files in files_modified that git status shows
were not modified this turn (test_metadata_filter.py, test_concurrent_writes.py, conftest.py …)
→ evidence gathering aborted → 3 turns, no recovery
```

**Root cause**
The task's work was genuinely complete (its 5 metadata/concurrency tests pass in 7.5s; the AC-006 parallel-isolation doc exists in `conftest.py`). But files committed in **earlier turn checkpoints** show as "no changes this turn" to the honesty checker, which short-circuits evidence gathering. A reporting-hygiene artifact, not a code defect.

**Fix**
A clean `--resume` cleared it — TASK-MEM-012 approved on the fresh run (2 turns), then TASK-MEM-013 approved (1 turn) → SUCCESS. Same recovery pattern that cleared the earlier tasks (MEM-002, MEM-006, MEM-010 all approved in 1 turn on their clean re-run).

---

## What went right

- **Ground-truthing beat every gate verdict.** On each "failure" I ran the pinned test command directly (worktree venv, and post-merge the main venv) — that's what revealed 6 of 8 were false-positives and isolated the 1 real bug. Never trusted a `FAILED`/`UNRECOVERABLE` at face value.
- **Reading the guardkit source** (`environment_bootstrap`, `coach_validator`, `agent_invoker._scan_ac_for_missing_paths`, `feature_orchestrator`) pinned each root cause instead of guessing.
- **`--resume` is the workhorse.** Only `completed` tasks are skipped; failed ones re-execute, and a clean restart reliably clears the honesty/transient stalls without code changes.
- The one genuine bug (Error 5) was a **real find** — the gates earned their keep there.

## Prevention / follow-ups

1. **Install Python ≥3.12 as a uv-managed interpreter** (`uv python install 3.14`) so bootstrap stops defaulting to 3.10. (Error 1)
2. **`.guardkit/config.yaml` `coach.test_execution: subprocess` is committed (`0ca7feb`) — keep it.** Without it every Coach verification on this machine fails silently. (Error 2)
3. **Author ACs so commands/paths don't form one backtick span ending in a path token.** Put the pattern and each path in separate backticks; prefer bare paths or matching label==href in markdown links. (Error 3; same class as FEAT-MEM-07 Error 2)
4. **Don't hand-copy `features/` into a worktree** to satisfy one file — it can drag in `.feature` files that trip the BDD gate. Copy only what's needed. (Error 4)
5. **Export `FLEET_MEMORY_EMBED_URL=http://promaxgb10-41b1:9000`** when launching AutoBuild or running integration tests, or those ACs skip → reject. (Error 6)
6. **Launch with `>> log 2>&1; echo EXIT_CODE=$?`, not `tee`,** so a silent orchestrator death is visible. (Error 7)
7. **A green Coach is necessary, not sufficient** — re-run the full suite in the worktree venv before `/feature-complete`, and again in the **main** venv post-merge.
8. **Upstream candidates for guardkit** (remove false-positives at source): default `coach.test_execution` to subprocess when the SDK runner produces no Bash call; plan_audit should not treat a backtick *command* as a path; honesty `claim_audit` should not abort on files modified in earlier-turn checkpoints.
9. **TASK-MEM-008 operator handoff still owed** — run `deploy/nas/deploy.sh` + `smoke.sh` from the Mac (gates G0,G2–G6), then `/task-complete TASK-MEM-008`.
