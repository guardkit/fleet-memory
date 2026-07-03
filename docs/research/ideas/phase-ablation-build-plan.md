# Memory Value Ablation — Build Plan (Phase ABL)

## Status (2026-07-03)

- Authored same day §2 of the scope was verified from source (neither §2.1 stop
  condition fired — see scope §2.1 outcome block for the numbers).
- **Nothing in this plan is started.** Gate order: Rich reviews this plan →
  Rich freezes §5 → FEAT-ABL-002 spike → pipeline features. FEAT-ABL-002 does
  not start before the review.
- Session memory notes updated: the FEAT-MEM-04 "JetStream gap open" note was
  stale (closed 2026-06-24→27); the regression task pins the historical SHA.
- **2026-07-03 (evening): FEAT-ABL-002 spike EXECUTED — Harbor ADOPTED.**
  P1 gate met: oracle rollout on the FEAT-9DDE spike task scored reward 1.0
  on the GB10 via Harbor 0.17.0 (`-e docker`, ARM64 image, llama-swap route
  proven in-container). Fallback not triggered. Contract frozen with one
  correction: Harbor's test dir is `tests/` (plural). Ran on Spark A, not
  Spark B — no GB10→Spark B key auth exists (alias verified from another
  host); scope §4 acceptance reads "on the GB10" and its GPU was idle.
  Runbook: fleet-evals `docs/runbooks/FEAT-ABL-002-spike.md`.
- **2026-07-03 (later, same day): `fleet-evals` now EXISTS** — created ahead of
  Step 3 to house the **PO held-out suite** (scope §6b's deadline clause):
  4 doc-shaped tasks on the task-folder contract, oracle-validated + red-teamed,
  33/33 verifier-integrity + 22/22 oracle-gate green (independently re-run
  2026-07-03). Uncommitted pending Rich's §5 freeze of
  `fleet-evals/docs/research/ideas/po-heldout-suite-scope.md` (freeze = the
  commit). Step 3's repo bootstrap is superseded; ABL-003/004 land in the
  existing repo. Doc-shaped tasks use `input/` in place of `environment/`;
  ablation tasks are agentic and still need `environment/` Dockerfiles — the
  two shapes coexist under `tasks/`.

## Repo: **fleet-evals (NEW sibling — decision below)** · guardkit (ABL-001) · fleet-memory (ABL-005) · ops (Spark A/B)
## Scope doc: `phase-ablation-scope.md` (same directory) — §5 verdict is Rich's to freeze, untouched here

---

## Substrate home: `fleet-evals` as a new sibling repo — CONFIRMED

The scope's recommendation stands; verification strengthened it:

1. **Don't house the yardstick inside the thing being measured.** The ablation
   grades fleet-memory itself, and a failed §5 verdict descopes fleet-memory to
   a write-only log — the eval substrate must survive that descope untouched.
   fs-01 exists precisely because instrument and subject shared a home.
2. **§6 consumers span ≥3 repos** (QA-Verifier calibration → guardkit/forge;
   fine-tune gate suites → dataset-factory/coach-ft + the PO fine-tune;
   false-green corpus → incidents from fleet-memory, guardkit, forge;
   backward-edge → fleet-memory). No producer repo is a neutral owner.
3. **Task images pin *other* repos at historical SHAs** (guardkit @ pre-FEAT,
   fleet-memory @ pre-fix). Building those images from inside one of the pinned
   repos' own working trees invites exactly the state-contamination Harbor's
   clean-room design exists to prevent.
4. The forge proposer-eval corpus (`forge/docs/research/proposer-eval/corpus/`,
   fs-01/ff-01/ff-03/ff-05/ff-07) migrates in as the first §6c entries rather
   than growing a second corpus in a product repo.

`fleet-evals` does not exist yet (verified 2026-07-03). Created at
`~/Projects/appmilla_github/fleet-evals` during Step 3.

## Prerequisites

- [ ] **P0 (GATE): Rich reviews this plan, then freezes §5** — run 1 is blocked
  until the verdict is frozen; features ABL-001..005 may proceed after plan
  review, ABL-006 may not start before the freeze.
- [x] **P1 (GATE): FEAT-ABL-002 spike exit** — **met 2026-07-03**: one task
  (`abl-spike-001-task-status-json`), one Harbor rollout, reward **1.0**, on
  the GB10 (Spark A — no key auth from GB10 to Spark B existed; scope §4 says
  "on the GB10" and the GPU was idle, so acceptance met verbatim; see runbook
  §deviation). Harbor 0.17.0 adopted; fallback not triggered. The task-folder
  contract (task.toml / instruction.md / environment/ / **tests/** /
  solution/ — Harbor uses `tests/`, plural) is **frozen**; ABL-003/004 build
  against it. Evidence: fleet-evals `docs/runbooks/FEAT-ABL-002-spike.md`.
- [ ] **P2: Compute window** — Spark A is running the PO pilot (GPU 95%,
  since 08:00 2026-07-03) with the 82h run pending go/no-go behind it.
  Default rollout host: **Spark B** (idle, aarch64, Docker 29.2.1, proven
  route to Spark A `:9000`). Accepted risk: inference contention with the 82h
  run — fallback is installing llama-swap on Spark B (models already on NAS)
  or taking the post-82h window on Spark A. Decide at ABL-006 time; blocks
  nothing earlier.
- [ ] **P3: Fixture source creds** — live DSN recoverable via
  `docker inspect fleet-memory-relay` on GB10 (`Dell-ProMax` SSH alias); store
  at `whitestocks.tailebf801.ts.net:5433`. Verified working 2026-07-03.
- [ ] **P4: On-arm env contract** — rollouts must set `FLEET_MEMORY_ENABLED=true`,
  `FLEET_MEMORY_PG_DSN=<fixture>`, **`FLEET_MEMORY_EMBED_MODEL=nomic-embed-text-v1.5`,
  `FLEET_MEMORY_EMBED_DIMS=768`** explicitly: the guardkit adapter's defaults
  (`"embed"`, 1024 — `fleet_memory_client.py:620-645`) do not match the live
  store and would silently degrade the on-arm. Config hash per rollout records this.

## Feature summary

| # | Feature | Repo | Depends on | Est. | Status (2026-07-03) |
|---|---------|------|-----------|------|---------------------|
| 1 | FEAT-ABL-002 — Harbor spike on Spark (direct session, **no pipeline**) | ops/fleet-evals | P0 review | **1 day timebox** | ✅ **done 2026-07-03 — Harbor 0.17.0 ADOPTED** (fallback not triggered). Oracle rollout on the FEAT-9DDE spike task: reward **1.0** on the GB10; RED 7/7 → GREEN 7/7 oracle gate; ARM64 image native; container→llama-swap 200. Contract frozen (note: `tests/` plural, not `test/`). Evidence: fleet-evals `docs/runbooks/FEAT-ABL-002-spike.md`, `tasks/abl-spike-001-task-status-json/`, `spike/rollouts/` |
| 2 | FEAT-ABL-001 — retrieval arm switch + retrieval logging | guardkit | none (parallel to 3) | 0.5–1 day | ⬜ |
| 3 | FEAT-ABL-005 — fixture tooling (snapshot/hash/temporal cut/scratch ns) | fleet-memory | none (parallel to 2) | 1 day | ⬜ |
| 4 | FEAT-ABL-003 — AutoBuild agent adapter | fleet-evals | ABL-002 (contract), ABL-001 (arm env) | 0.5–1 day | 🟨 **skeleton merged 2026-07-03** (fleet-evals `fc574eb`): Harbor custom agent + per-rollout JSON emitter, smoke-proven reward 1.0 with P4 env injection; ABL-001-dependent seams marked `SEAM(ABL-001)` in `adapter/` |
| 5 | FEAT-ABL-004 — task corpus ×10, Oracle-validated | fleet-evals | ABL-002 contract; **go/no-go after task 3** | 3–7 days (dominant cost) | 🟨 **3/10 done, go/no-go = GO 2026-07-03** (FEAT-9DDE `26722cb`, fs-01 `418b3bd`, FEAT-FAUD `a0c85a0`; all oracle reward 1.0) |
| 6 | FEAT-ABL-006 — 60 rollouts + RESULTS doc | ops/fleet-evals | ABL-001..005, **§5 frozen**, P2 window | 20–40 GPU-h + 0.5 day | ⬜ |

Ordering note: the spike goes first because it is the only cheap kill left —
if neither Harbor nor the fallback can produce a reward score on aarch64, the
corpus investment (the real cost, §3.2) never starts. ABL-001 and ABL-005 are
independent of the spike *and of each other* and can run as pipeline features in
parallel with corpus authoring once the contract is frozen.

## GuardKit command sequence

> Run each `/feature-spec` from the named repo root. Context paths verified to
> exist 2026-07-03. The spike is a direct session step — no `/feature-spec`,
> no autobuild.

### Step 0 — FEAT-ABL-002: Harbor spike (direct session on Spark B, timebox 1 day)
```
ssh Spark                      # spark-fcf6, aarch64, Docker 29.2.1
python3 -m venv ~/harbor-venv && ~/harbor-venv/bin/pip install harbor
# 1. run one Harbor sample task end-to-end with -e Docker
# 2. author one ARM64 task image (FROM an arm64 python base; repo pinned via
#    git archive <pre-FEAT sha>), prove `docker build` on aarch64
# 3. in-container: curl http://promaxgb10-41b1:9000/health  (llama-swap route;
#    if container DNS misses the LAN name, --add-host or the Tailscale IP)
# 4. one rollout, one reward score collected
```
**Exit:** one task, one rollout, one reward, on Spark. **Pre-declared fallback**
(if blocked past the timebox): a harness-native runner in fleet-evals honouring
the **identical task-folder contract** — Docker run per rollout, PyTest reward,
per-rollout JSON — so the corpus stays Harbor-portable. Declare which path won
in the runbook; either satisfies scope §8.1.

### Step 1 — FEAT-ABL-001 (guardkit repo root)
```
/feature-spec "Retrieval arm switch + structured retrieval logging for the \
memory ablation (scope §4 FEAT-ABL-001). Add FLEET_MEMORY_RETRIEVAL=off|fixture:<id> \
read in _load_fleet_config_from_env; enforce INSIDE FleetMemoryClient.search \
(return [] exactly like the enabled=false gate at lines 255-256) so the \
AutoBuildContextLoader, turn-continuation state and template-pattern paths \
stay byte-identical between arms — do NOT reuse --no-context or \
FLEET_MEMORY_ENABLED=false, which null the whole loader. Emit a structured \
per-call JSONL retrieval log with per-item natural_key + score, captured \
between fm_search() and assemble_context() where per-item identity still \
exists (search currently collapses to one synthetic uuid4 hit at 310-316); \
extend query_logger with an items:[{id,score}] field and call it from the \
AutoBuild chain. fixture:<id> resolves the fixture DSN via env; off-arm \
acceptance: zero retrieval-log entries; fixture-arm: item ids + scores logged; \
ContextStatus identical across arms." \
  --context guardkit/knowledge/fleet_memory_client.py \
  --context guardkit/knowledge/query_logger.py \
  --context guardkit/knowledge/autobuild_context_loader.py \
  --context ../fleet-memory/docs/research/ideas/phase-ablation-scope.md
/feature-plan FEAT-ABL-001
guardkit autobuild FEAT-ABL-001
```
Validation: unit tests assert the three arm states (`unset`→current behaviour,
`off`→empty results + no log entries + loader still constructed, `fixture:<id>`
→ DSN swap + items logged); one manual smoke autobuild per arm diffing
`ContextStatus` and the retrieval log.

### Step 2 — FEAT-ABL-005 (fleet-memory repo root)
```
/feature-spec "Fixture tooling for the memory ablation (scope §4 FEAT-ABL-005): \
pg_dump-based snapshot of the live store to a versioned fixture with content \
hash (same fixture id => byte-identical retrieval corpus); restore into a \
per-run Postgres; per-task temporal-cut filter driven by \
episode_meta.occurred_at — NOT row created_at, which is backfill-era \
(2026-06-28+) — excluding entries with occurred_at >= the task's FEAT start \
date AND all 176 null-occurred_at entries (distilled build_outcomes/ADRs \
reference MEM08-era work: answer-key risk); scratch namespace for rollout-time \
writes, discarded per rollout. Acceptance: hash stability; the cut for a \
2026-06-25 task (FEAT-HARV) demonstrably excludes the OUT-SMOKE build_outcome \
(occurred_at 2026-06-29) and all null-timestamped entries." \
  --context src/fleet_memory/store.py \
  --context src/fleet_memory/settings.py \
  --context src/fleet_memory/retrieval/core.py \
  --context deploy/local/docker-compose.yml \
  --context docs/research/ideas/phase-ablation-scope.md
/feature-plan FEAT-ABL-005
guardkit autobuild FEAT-ABL-005
```
Validation: restore→hash→restore round-trip byte-identical; temporal-cut unit
tests against a seeded store copy; null-exclusion count == 176 on fixture v1.

### Step 3 — FEAT-ABL-003 (fleet-evals repo root)
```
# Repo bootstrap DONE 2026-07-03 (see Status): fleet-evals exists with the
# task-folder contract live (PO held-out suite) and guardkit scaffolding.
/feature-spec "AutoBuild agent adapter behind the spike-frozen task-folder \
contract: given a task dir, launch the environment container, run \
guardkit autobuild <task> --coach-model <pinned> --model <pinned> inside it, \
arm selected via FLEET_MEMORY_RETRIEVAL env (P4 env contract applied), copy \
out the retrieval log + config hash, run test/ PyTest for the reward, emit \
per-rollout JSON {task, arm, rep, reward, retrieval_items, config_hash, \
wallclock, tokens}. Local only per DF-001 — no cloud tracking on the \
critical path." \
  --context ../guardkit/guardkit/cli/autobuild.py \
  --context ../fleet-memory/docs/research/ideas/phase-ablation-scope.md \
  --context <spike-produced sample task dir>
/feature-plan FEAT-ABL-003
guardkit autobuild FEAT-ABL-003
```
Validation: adapter runs the spike's sample task to a terminal state and the
reward + retrieval log land in the per-rollout JSON (scope §4 acceptance).

### Step 4 — FEAT-ABL-004: task corpus (fleet-evals; authoring-heavy)
First three tasks — deliberately one regression + two easy-medium guardkit
FEATs to calibrate packaging cost before the go/no-go:
1. **fs-01** (regression): fleet-memory pinned pre-`app.py:86` fix; grader =
   full-unit-suite gate goes RED where the original Coach went GREEN
   (forge `GOLD.md` verify.sh sketch is the starting point).
2. **FEAT-9DDE** (guardkit, easy-medium, pre-FEAT `3450f602c`).
3. **FEAT-FAUD** (guardkit, easy-medium, pin parent `71db6d268`).

**Go/no-go after task 3** (scope §3.2): >~1 day/task with no downward trend →
stop, re-scope corpus size. Then the remaining seven per Appendix A. Every task
passes its Oracle (landed diff applied → tests green) before it may grade.

> **Go/no-go outcome (2026-07-03): GO.** Packaging costs: FEAT-9DDE ~1.5 h
> (inside the spike; promoted to corpus row 1, fleet-evals `26722cb`), fs-01
> ~40 min (`418b3bd`), FEAT-FAUD ~25 min (`a0c85a0`) — far under the
> ~1 day/task threshold with a clear downward trend. All three RED/GREEN
> oracle-validated with Harbor oracle-rollout reward 1.0 each; evidence in
> each task's `oracle-validation.md` + `validation/`. Pattern per task:
> `prepare_context.sh` + sha256-pinned gitignored tarball + independent
> black-box verifier. Remaining seven proceed per Appendix A.

### Step 5 — FEAT-ABL-006: run + RESULTS (ops; needs §5 frozen)
- Fixture v1 snapshot + hash recorded; llama-swap warm-model note in runbook
  (keepalive timer currently paused — decide with the 82h scheduling).
- 2 arms × 10 tasks × K=3, paired, fresh container per rollout; per-rollout
  JSON + config hash; validity guardrail (≥1 retrieved item per on-arm
  rollout) checked **during** the run, not after.
- `RESULTS-phase-ablation-<date>.md` per scope §4/§8.4: paired table, deltas,
  guardrail, §5 verdict applied verbatim, Coach-vs-verifier agreement table,
  root-cause note for any task where memory-on did worse. Rich's relevance
  spot-audit: one rep per task.

## Files that will change (primary)

| File | Feature | Change |
|---|---|---|
| `guardkit/guardkit/knowledge/fleet_memory_client.py` | ABL-001 | `FLEET_MEMORY_RETRIEVAL` in `_load_fleet_config_from_env` (:620); arm gate + per-item log emit inside `search()` (:302-316) |
| `guardkit/guardkit/knowledge/query_logger.py` | ABL-001 | `items:[{id,score}]` schema field + AutoBuild-chain caller |
| `fleet-memory/scripts/fixture_snapshot.py` + `src/fleet_memory/fixture/` (new) | ABL-005 | snapshot/restore/hash/temporal-cut/scratch-ns |
| `fleet-evals/` (new repo) | ABL-003/004/006 | `adapter/`, `tasks/<id>/{task.toml,instruction.md,environment/,test/,solution/}`, `runbooks/`, `RESULTS-…md` |
| `forge/docs/research/proposer-eval/corpus/…` | ABL-004 | fs-01 (+ siblings later) migrate to fleet-evals; pointer left behind |

No fleet-memory retrieval-code changes: the toggle lives in guardkit's client;
the store/retrieval stack is the *subject* and stays untouched (scope §7).

## Timeline

Spike day 1 (P1). ABL-001 ∥ ABL-005 days 2–3. fleet-evals bootstrap + ABL-003
days 3–4. Corpus days 4–10 with the go/no-go at ~day 6. Run when the P2 window
opens (pilot → 82h go/no-go decides Spark B-with-contention vs post-run
Spark A); RESULTS within one week of run 1 (scope §8.4). Everything after the
spike is off Rich's critical path except the §5 freeze and the relevance
spot-audit.

---

## Appendix A — candidate FEAT table (verified from source 2026-07-03)

Selection per scope §3.2: ≥7 memory-relevant + 3 known false-greens, mixed
difficulty, no task chosen to flatter either arm. "Predating entries" = live-store
entries with `episode_meta.occurred_at` strictly before the FEAT start date
(SQL against the NAS store, 2026-07-03). Store covers **guardkit only**, so
memory-relevance ⇒ guardkit FEATs.

### Proposed corpus (10)

| # | Task | Repo | Start→End | Pre-FEAT pin | Spec source | Landed behaviour a PyTest asserts | Mem-relevant (predating) | Difficulty |
|---|------|------|-----------|--------------|-------------|-----------------------------------|--------------------------|------------|
| 1 | FEAT-9DDE `--json` task-status producer | guardkit | 2026-06-11→13 | `3450f602c` | `.guardkit/features/FEAT-9DDE.yaml` + TASK-TSJ-001/002 mds | `task_status_json.py` emits schema-v1, byte-stable, sorted JSON | ✅ 1,027 | easy-med |
| 2 | FEAT-FAUD stale feature-YAML auditor | guardkit | 2026-06-16 | `71db6d268` (parent of spec commit) | `FEAT-FAUD.yaml` + TASK-FAUD-001..003 | `feature_audit.py` infers status from task locations; CLI exits 1 on stale w/o `--fix` | ✅ 1,123 | easy-med |
| 3 | FEAT-HARV memory harvest publisher | guardkit | 2026-06-25→26 | `e43ffa8c9` | P4 feature brief + `FEAT-HARV.yaml` | walker/taxonomy/publisher modules; deterministic episode_id idempotency; NATS seam mocked | ✅ 1,173 | medium |
| 4 | FEAT-C332 Coach wiring-evidence bundle | guardkit | 2026-06-12 | `bea0da142` | `git show 05fa5f3c6:.guardkit/features/FEAT-C332.yaml` + TASK-QAWE mds | mocked-seam detection + SPEC_GAP hard guard in orchestrator | ✅ 1,045 | medium |
| 5 | FEAT-ATR timeout/budget reconciliation | guardkit | 2026-04-30 | `712896c1e` | `.guardkit/archive/FEAT-ATR/` + TASK-ATR-001..003 mds | `task_timeout` frontmatter override; budget refresh between Phase 4/5; late-approval reconcile | ✅ 947 | medium |
| 6 | FEAT-4396 template pattern loader | guardkit | 2026-04-11 | `29709e435` (fork point — both merge parents carry FEAT work) | `FEAT-4396.yaml` + TASK-TPL mds | loader + domain-hint selector wired into context loader | ✅ 706 | medium |
| 7 | FEAT-CF57 AutoBuild instrumentation | guardkit | 2026-03-02→03 | `564b16c07` | `FEAT-CF57.yaml` + TASK-INST-001..010 + Gherkin | event schemas, JSONL/NATS emitters, redaction, digests | ✅ 423 | hard |
| 8 | **fs-01** Coach false-approval (regression) | fleet-memory pin | incident 2026-06-13 | pre-`app.py:86`-fix state | forge corpus `fs-01…/GOLD.md` + raw traces `.guardkit/autobuild/TASK-RLY-006/*` | full-suite gate RED where Coach said GREEN; fix restores green (encodes "full suite, not new-module tests") | — regression | n/a |
| 9 | **MEM-04 JetStream gap** (regression) | fleet-memory pin | gap closed 06-24 | pre-`0951620` | TASK-RLY-007 md + `MEM-04-relay-jetstream-contract.md` | durable consumer exists on MEMORY stream; episode survives restart; poison → DLQ; unit-green alone insufficient | — regression | n/a |
| 10 | **MEM-05 parity harness** (regression) | fleet-memory | broken at HEAD `2f372f4` | `bb92ed2` or HEAD (state unchanged) | `probe_harness.py` + `eval/probe_set.json` + forge QAV Phase-0 doc | `load_probe_set` exists and yields ≥15 ProbeQuery (baselines present); runner writes ParityReport artifact; currently RED while unit tests GREEN | — regression | n/a |

Memory-relevant count: **7** (rule: ≥7) ✅ · false-greens: **3** (rule: ≥3) ✅ ·
difficulty mix: 2 easy-med / 4 medium / 1 hard / 3 regression.

### Alternates (swap-ins if packaging cost or Oracle validation kills a row)

| Task | Repo | Start | Pre-FEAT pin | Mem-relevant (predating) | Note |
|------|------|-------|--------------|--------------------------|------|
| FEAT-AC1A seam-first testing | guardkit | 2026-02-14 | `723e5f4e4` | ✅ 394 | deliverable is largely tests — grade on suite presence + green |
| FEAT-FMT fastmcp-python template | guardkit | 2026-01-24 | `5b5286ef2` | ✅ 306 | distinguish from same-day fastapi-mcp template in grading |
| FEAT-GI Graphiti integration | guardkit | 2026-01-24 | `fb6e7c733` | ✅ 306 | surface deleted by FEAT-MEM-09 — graders come from the 2026-01-29 tree |
| FEAT-MEM-09 Graphiti decommission | guardkit | 2026-07-01 | `fdc55af3d` | ✅ 1,180 | scope to WS-2/2c code workstreams; null-exclusion mandatory (MEM08/09-era distilled outcomes) |
| FEAT-RBX runbook executor | forge | 2026-06-22 | `bc90bc4` | ✗ (no forge entries) | strongest non-guardkit candidate if corpus rebalances |
| TASK-FRR wave (TDD red→green) | jarvis | 2026-05-01 | `08a6974` | ✗ | repo's own red tests are ready-made graders |
| TASK-FIX-RELAYDROP01 embed-400 DLQ | fleet-memory | 2026-06-26 | `d9484c9` | ✗ | ideal small bugfix eval |
| FEAT-MEM-05-PARITY chunker/assembly fix | fleet-memory | 2026-06-28 | `ad01e5b` | ✗ | pin commit itself contains the failure analysis as spec |

Full sweep: 49 candidates (guardkit 12 / forge 12 / jarvis 13 / fleet-memory 12),
~42 strong; every pre-FEAT SHA `rev-parse`-verified; three fleet-memory pins
ground-truthed buildable (`git archive` → 78/273/505 unit tests green). Notable
exclusions: FEAT-HMIG (no pinnable pre-state), FEAT-E2CB (no landing commit on
main), FEAT-JARVIS-001 (pre-FEAT tree is docs-only), FEAT-CA81 (greenfield —
viable only if empty-repo starts are supported). Full per-repo sweep JSON:
session workflow `wf_90cc0727-175` journal.
