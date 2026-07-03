# Memory Value Ablation — Scope (Phase ABL) — v2

**Status:** DRAFT v2 (Desktop-authored 2026-07-03). **v1 retracted same day** after review found three design holes (§1.1). §2 **verified from source 2026-07-03** (Claude Code, per §2.1) — **neither stop condition fired**; `phase-ablation-build-plan.md` authored (same directory). Awaiting Rich: build-plan review, then §5 freeze. No build work (including FEAT-ABL-002) before review.
**Date:** 2026-07-03
**Repo focus:** fleet-memory (retrieval toggle) · guardkit (AutoBuild agent adapter) · **NEW: `fleet-evals`** (recommended home for the substrate + task corpus — cross-repo consumer count in §6 argues for its own repo; confirm in build plan)
**Decision frame:** DF-001 (local loop; cloud tracking optional, never authoritative) · DF-008 (evidence-before-investment applied to our own infrastructure) · DF-006 (the Oracle/golden-set philosophy, made operational) · ADR-FLEET-002 (tests the prior question)
**Companions:** `~/Projects/YouTube Channel/insights/Harbor - Open Source Agent Evaluations in Sandboxed Real Environments.md` (substrate reference) · UBS scope §7.3 (harvest-corpus shape)

---

## 1. Objective

Answer, with numbers: **does fleet-memory retrieval measurably improve AutoBuild outcomes?** — measured on an eval substrate that outlives this phase and becomes the fleet's standing evaluation infrastructure (§6).

### 1.1 Why v1 was retracted

1. **Empty-memory precondition.** v1 never specified the memory state the on-arm retrieves from. With an unspecified or empty store, both arms are identical and a null result is guaranteed — an expensive way to measure nothing.
2. **Coach as primary grader.** v1's primary metric was Coach score — grading memory with the instrument fs-01 already proved foolable. The shared-oracle problem, imported into the experiment designed to escape it.
3. **No repetition policy.** Single rollouts per task per arm on nondeterministic local models measures noise, not effect.
4. **(Found in v2 design) Answer-key leakage.** If the memory fixture contains entries written by or after the historical FEATs used as eval tasks, the on-arm retrieves its own solution summaries. Requires a per-task temporal cut (§3.3).

## 2. Current state (verified from source 2026-07-03)

> **⚠️ 2026-07-03 corrections (verified from source; UBS-scope style).** Three believed-states were wrong or stale:
> 1. **FEAT-MEM-04 "regression on disk" is stale.** The JetStream-durability gap was closed on main 2026-06-24→27 (`0951620` durable pull consumer, `abe48c3` DLQ on deterministic embed-400, `55a0cda` settings-driven ack_wait; `MEMORY` stream now in `nats-infrastructure/streams/stream-definitions.json:70-79`; TASK-RLY-007 moved to completed in `3ca17be`). The regression task must **pin the pre-`0951620` state** — it no longer exists at HEAD.
> 2. **`phase-core-build-plan.md` — the row's named verification reference — is itself ~3 weeks stale** (banner still says 2026-06-13, MEM-04..09 "Not started"). Git reality: MEM-02..07 all merged (`3655188`, `c6c6983`, `c041059`, `bb92ed2`, `fc0ea94`, `373dc97`), MEM-08 landed guardkit-side (`764068de6`), MEM-09 in progress. The believed state "Built" was right; the reference doc was not.
> 3. **GB10 "82h pending go/no-go" was overtaken same-day:** a PO pilot has been running since 08:00 (GPU 95%). Keepalive-paused belief confirmed.

| Component | Believed state (2026-07-03) | Verified 2026-07-03 |
|---|---|---|
| fleet-memory core (Postgres/pgvector) | Built per phase-core | **✅ confirmed** (reality ahead of the stale plan doc — see banner #2). Unit suite at HEAD `2f372f4`: **620 passed, 2 skipped, 73 integration-deselected** (`.venv/bin/python -m pytest tests/ -m "not integration"`, 12s). Retrieval stack present: `src/fleet_memory/retrieval/{core,assembly,composition,search_request}.py`; MEM-05 parity eval PASS `be1f125` |
| AutoBuild → retrieval touchpoint | Exists at context-load | **✏️ corrected — exists, and a toggle already exists, but with the wrong blast radius.** Call chain: `guardkit/orchestrator/autobuild.py:1351` (factory, gated by `enable_context`) → `:5478` player / `:5706` coach context load → `knowledge/autobuild_context_loader.py:333` → `knowledge/fleet_memory_client.py:302` (`fleet_memory.retrieval.search` + `assemble_context`). Two switches exist — `FLEET_MEMORY_ENABLED` env, default **false** (`fleet_memory_client.py:627`), and `--enable-context/--no-context` CLI (`cli/autobuild.py:300-303`, `750-753`) — but **both null the entire context loader** (turn-continuation state included), violating FEAT-ABL-001's "no other code-path divergence". Per-item retrieval logging is **absent on the AutoBuild path**: `query_logger.py` is only called from `/feature-plan`, and `fleet_memory_client.py:310-316` collapses results to one synthetic hit (fresh `uuid4()`, aggregate score) before any caller sees item ids. **FEAT-ABL-001 stands as spec'd** (in-client `FLEET_MEMORY_RETRIEVAL` gate + `items:[{id,score}]` logging). Operational note: guardkit's `.env` sets no `FLEET_MEMORY_*`, so today's default AutoBuild runs are effectively off-arm |
| Memory store contents | Unknown size/coverage | **✏️ verified** (live NAS store `whitestocks.tailebf801.ts.net:5433`, DSN from `docker inspect fleet-memory-relay` on GB10). **1,356 entries, all `project=guardkit`**: chunk 679 (guardkit-harvest), document 499 (graphiti-migration), build_outcome 132, adr 46; `store_vectors` 1:1. Row `created_at` is all backfill-era (2026-06-28→07-02) — **useless as cut axis**; the temporal cut must run on `episode_meta.occurred_at`: chunks span **2025-10-28→2026-06-25**, documents **2026-03-05→2026-06-25**, zero nulls; **176 entries (distilled build_outcomes/ADRs + 4 auto_captured) have NULL `occurred_at`** and must be excluded or task_id→git backdated — several reference MEM08-era work (answer-key risk if naively included). Zero forge/jarvis/fleet-memory entries → memory-relevant tasks must be guardkit FEATs |
| Historical FEATs usable as tasks | Unknown count | **✏️ verified — exceeds threshold.** Sweep found **49 candidates** (guardkit 12, forge 12, jarvis 13, fleet-memory 12), **~42 strong** (verified pre-FEAT SHA + recoverable spec + testable landed behaviour; every pre-FEAT SHA `rev-parse`-verified; three fleet-memory pins ground-truthed by `git archive` + green pytest). **11 guardkit candidates are memory-relevant with 306–1,180 predating timestamped fixture entries each** (per-candidate counts in build-plan Appendix A) |
| Harbor on GB10 (ARM64) | Never installed | **✅ verified 2026-07-03 — spike executed, Harbor 0.17.0 ADOPTED** (was ⏭ deferred-to-spike). Installs clean on aarch64 (all-wheel, no compiles); sample task + FEAT-9DDE spike task ran end-to-end with the Docker environment; ARM64 task image built natively (`git archive`-pinned guardkit @ `3450f602c`); oracle rollout reward **1.0** on the GB10; in-container→llama-swap `:9000` = 200 both bare (MagicDNS) and via `--add-host …:host-gateway`. Task-folder contract frozen — one §3.2 correction: Harbor uses `tests/` (plural), not `test/`. Fallback not triggered. Evidence: fleet-evals `docs/runbooks/FEAT-ABL-002-spike.md`, `tasks/abl-spike-001-task-status-json/`, `spike/rollouts/` |
| Container → host llama-swap networking | Unknown | **✅ desk-check passed.** llama-swap runs `-listen :9000` — all interfaces (`ps` on GB10 2026-07-03: `/usr/local/bin/llama-swap -config /opt/llama-swap/config/config.yaml -listen :9000 -watch-config`); child llama-servers bind `0.0.0.0`. Cross-machine proven: Spark B → `http://promaxgb10-41b1:9000/health` = **200**. In-container proof lands in the spike |
| FEAT-MEM-04 / MEM-05 / fs-01 artefacts | Regression + broken harness on disk | **✏️ corrected — one of three regressions still on disk.** **fs-01**: packaged as forge proposer-eval corpus item (`forge/docs/research/proposer-eval/corpus/fs-01-coach-false-approval-partial-run/`, commit `25a82ed`); raw traces at `fleet-memory/.guardkit/autobuild/{FEAT-MEM-04-build.log, TASK-RLY-006/*}`; symptom fixed on main (`app.py:86`) → task pins the pre-fix state. **MEM-04**: gap closed (banner #1) → task pins pre-`0951620`. **MEM-05 harness**: **confirmed still broken at HEAD `2f372f4`** — no runner script; `load_probe_set` referenced (`probe_harness.py:92`) but defined nowhere; `eval/probe_set.json`'s 16 probes lack the required `baseline_answer` field; `PARITY_TOLERANCE=0`. The parity *gate* later passed via a separate LLM-judge eval (`docs/evals/FEAT-MEM-05-parity-eval-2026-06-27.md`), never via this harness — the canonical unit-green/e2e-dead false-green, gradeable at HEAD |
| GB10 capacity | 82h dataset-factory run pending go/no-go; keepalive paused | **✏️ corrected** (banner #3). 82h run not started; **PO pilot live since 08:00 2026-07-03** (`agentic-dataset-factory` `agent.py`, GPU 95%, `output/train.jsonl` growing at 11:46). `llama-swap-keepalive.timer` **inactive** (last fired 06:15 BST 2026-07-03). **Spark B** (`spark-fcf6`): idle (GPU 0%), `aarch64`, Docker 29.2.1, reaches Spark A `:9000`, **no local llama-swap** — candidate rollout host while Spark A is busy |

### 2.1 Verification protocol (executed by Claude Code before anything else)

For each §2 row, verify from source using the method below; annotate the row **confirmed / corrected / deferred-to-spike** with evidence (file:line, commit SHA, DB stats). Flip the §2 banner to "verified from source <date>". Any wrong believed-state gets a dated correction banner (UBS-scope style, 2026-07-02 exemplar).

| Row | Method | Evidence recorded |
|---|---|---|
| fleet-memory core | Read `phase-core-build-plan.md` status + feature table; run the repo test suite | Per-FEAT status, commit refs |
| Retrieval touchpoint | Grep fleet-memory client + `../guardkit` for the retrieval call at context assembly; identify config surface | Call site file:line; toggle exists Y/N → sets FEAT-ABL-001 shape |
| Store contents | Query the live Postgres store (host/creds: confirm with Rich if not in config) | Entry count, per-repo counts, timestamp min/max, entry types |
| Candidate FEATs | `git log --grep FEAT-` + `.guardkit/features/` sweep across guardkit/forge/jarvis/fleet-memory | Candidate table (≥10 rows): FEAT id, repo, pre-FEAT SHA, spec source path, observable behaviour, memory-relevance — lands as build-plan appendix |
| Harbor on GB10 | **Deferred-to-spike** (FEAT-ABL-002 *is* the verification) | Marked as such |
| Container→host networking | Desk-check llama-swap bind address/config now; full proof in spike | Bind config ref |
| MEM-04 / MEM-05 / fs-01 | Locate artefacts; current state, branch/commit | Refs |
| GB10 capacity | Pilot/82h status + keepalive timer state (Rich supplies or SSH check) | Noted |

**Stop conditions — report to Rich and do NOT author the build plan if either fires:**
1. Store too thin to satisfy the ≥7 memory-relevant selection rule (§3.2) — i.e., fewer than 7 candidate tasks have related fixture entries predating them.
2. Fewer than 10 viable candidate FEATs.

Either finding re-scopes or kills the phase; per §5's philosophy, killing it cheaply is a successful outcome. Only if no stop condition fires does the session proceed to author `phase-ablation-build-plan.md`.

**Outcome (executed 2026-07-03):** protocol run in full (7 parallel verification agents + live-store SQL + GB10/Spark-B SSH checks). **Stop condition 1 CLEAR** — 11 guardkit candidates have 306–1,180 related timestamped fixture entries predating them (rule needs ≥7). **Stop condition 2 CLEAR** — ~42 strong candidates across the four repos (rule needs ≥10). Build plan authored: `phase-ablation-build-plan.md` (same directory), candidate table in its Appendix A.

## 3. Design

### 3.1 Substrate: Harbor (three pillars)

Per the insights doc: (1) every rollout in its own clean, isolated environment (Docker image as starting state); (2) deterministic pass/fail via PyTest asserting **environment state, not output strings**; (3) results tracked over time. Local execution (`-e Docker`) on the GB10. LangSmith tracking is optional convenience only — **the local RESULTS doc + per-rollout JSON are authoritative** (DF-001: no cloud service on the loop's critical path; observability may degrade, evidence may not).

### 3.2 Task corpus — N = 10 historical FEATs (the real cost of this phase)

Each task is a folder in the Harbor anatomy:

| Component | Content | Source |
|---|---|---|
| `task.toml` | timeout, CPU/memory limits | authored |
| `instruction.md` | the FEAT's original spec/feature text | repo history |
| `environment/` | Dockerfile: repo pinned @ pre-FEAT commit + toolchain + route to host llama-swap | repo history |
| `test/` | PyTest asserting observable behaviour of the **landed** implementation | authored from the landed diff — independent of the eval-time Player by construction |
| `solution/` | the landed diff | git |

**Oracle validation gate:** every task must pass its own tests when the Oracle solution is applied, *before* it is allowed to grade anything. A task whose Oracle fails is a broken verifier, not a hard task.

**Selection rule:** ≥7 tasks memory-relevant (repo history present in the fixture, so retrieval plausibly helps) + ≥3 known false-greens (fs-01, FEAT-MEM-04, the MEM-05 harness) whose tests encode the regression that originally slipped. Mixed difficulty; no task selected because it flatters either arm.

**Cost estimate:** 0.5–1 day per task for the first three, faster after. **Go/no-go checkpoint after task 3:** if packaging cost exceeds ~1 day/task with no downward trend, stop and re-scope corpus size before continuing. The cost is amortised across every §6 consumer — that is why it is worth paying and why v1's two-line version was hand-waving.

### 3.3 Memory fixture + leakage control

- Snapshot production fleet-memory → **versioned fixture** (dump + content hash). Same fixture for every on-arm rollout.
- **Per-task temporal cut:** for each eval task, fixture entries timestamped at or after that FEAT's start date are excluded. Without this, the on-arm retrieves its own completion records — the answer key.
- Fixture mounted read-only; rollout-time writes go to a scratch namespace discarded per rollout.
- **Validity guardrail:** every rollout logs retrieval calls (item ids, scores). An on-arm rollout is valid only if retrieval returned ≥1 item. **Relevance spot-audit:** Rich reviews the retrieved items for one rep of each task — mechanism evidence alongside outcome evidence.

### 3.4 Arms and repetitions

2 arms × 10 tasks × **K = 3 reps** = **60 rollouts**, paired per task. Identical everything except the retrieval toggle: pinned model versions + quants, identical prompts, config hash recorded per rollout, fresh container per rollout (Harbor default). K=3 is powered only to detect large effects — deliberately: an effect too small to show at K=3 is too small to justify further memory investment.

### 3.5 Grading

- **PRIMARY: reward** = deterministic PyTest pass (Harbor binary 1/0 per rollout).
- **SECONDARY (reported, non-gating):** iterations-to-acceptance, escalations/hard stops, wall-clock, tokens.
- **DIAGNOSTIC:** Coach score per rollout — producing a **Coach-vs-verifier agreement table**, the first QA-Verifier calibration dataset, essentially free (§6a). The Coach grades nothing here; it is itself being graded.

### 3.6 Compute

60 rollouts × est. 20–40 min ≈ **20–40 GPU-hours**. Spark B during the 82h dataset-factory run, or the post-run window. Keepalive/warm-model state noted in the runbook.

## 4. Features

### FEAT-ABL-001 — Retrieval toggle + retrieval logging
Env/config switch `FLEET_MEMORY_RETRIEVAL=off | fixture:<id>` at the verified touchpoint; structured retrieval log per rollout. **Acceptance:** off-arm rollout shows zero retrieval calls in its log; fixture arm logs item ids + scores; no other code-path divergence.

### FEAT-ABL-002 — Harbor spike on GB10 (timebox: 1 day)
`pip install harbor`, run one sample task end-to-end on ARM64, build one ARM64 task image, prove container→host llama-swap route. **Pre-declared fallback:** if blocked past the timebox, implement a harness-native runner honouring the **identical task-folder contract** (task.toml/instruction/environment/test/solution) so the corpus remains Harbor-portable. **Acceptance:** one task, one rollout, one reward score, on the GB10.

### FEAT-ABL-003 — AutoBuild agent adapter
Wrap `guardkit autobuild <FEAT> --coach-model <pinned>` behind Harbor's agent interface; arm selection via env. **Acceptance:** adapter runs an eval task to a terminal state and Harbor collects the reward.

### FEAT-ABL-004 — Task corpus
10 tasks per §3.2, each Oracle-validated. **Acceptance:** 10/10 Oracle passes; selection-rule metadata recorded per task.

### FEAT-ABL-005 — Fixture tooling
Snapshot/restore, content hash, per-task temporal-cut filter, scratch-namespace isolation. **Acceptance:** same fixture id ⇒ byte-identical retrieval corpus; temporal cut demonstrably excludes ≥1 known post-FEAT entry for a regression task.

### FEAT-ABL-006 — Run + RESULTS
Execute the 60 rollouts; `RESULTS-phase-ablation-<date>.md` (runbook genre): per-task paired table, aggregate deltas, guardrail check, verdict applied per §5, Coach-vs-verifier agreement table, root-cause note for any task where memory-on did worse.

## 5. Pre-registered verdict (Rich amends thresholds if needed, then freezes before run 1)

**Validity gate:** ≥80% of on-arm rollouts retrieved ≥1 item — else the run is **INVALID** (fix seeding/selection, restart). Invalid ≠ negative.

**Memory retrieval earns further investment iff, across the paired task set:**
- mean per-task reward delta (on − off) **≥ +0.10** (≥ one net task-equivalent), **and**
- **≤1 task** where memory-on is worse by more than one rep.

**If not met:** fleet-memory descopes to a **write-only outcome log** (retained — it is the substrate for the backward edge and harvest corpus); retrieval investment stops until a pipeline consumer demonstrates need with its own pre-registered measure; **backend parity is cancelled, not deferred.**

Secondary metrics never rescue a failed primary. Either outcome is phase success: the point is to stop carrying an unmeasured belief.

## 6. The substrate outlives the phase

Same task contract, four standing consumers:

- **(a) QA Verifier calibration.** The agreement table + 60 outcome-labelled rollouts are the first golden-set entries — DF-006's "frontier as one-time yardstick" made operational with a deterministic yardstick instead.
- **(b) Fine-tune gate evals.** Every fine-tune gets a pre-registered held-out suite on this contract *before deployment*: coach-ft-vN (code-shaped tasks), and the **incoming PO fine-tune** — doc-shaped tasks (schema validity, coverage-vs-reference build plans; PyTest handles both). **Deadline: the PO suite exists before the 82h run completes**, or its success is the next unmeasured belief. *Deadline met 2026-07-03:* suite built, oracle-validated and red-teamed in `fleet-evals` (4 tasks; 33/33 verifier-integrity + 22/22 oracle-gate green, independently re-verified); pending Rich's freeze of its own §5 (`fleet-evals/docs/research/ideas/po-heldout-suite-scope.md`).
- **(c) Permanent false-green regression corpus.** fs-01, FEAT-MEM-04, MEM-05 as tasks that never leave the suite; every future wild catch joins them.
- **(d) Backward-edge evaluation (future).** Fixture version becomes the variable: does *richer* memory improve reward — the compounding-asset claim, tested the same way.

## 7. Explicitly out of scope

Graphiti parity · retrieval-strategy tuning (eligible only after a positive §5 verdict, as its own scope with its own verdict) · LangSmith cloud parallel execution (local Docker only; tracking optional, local results authoritative) · RL/optimization use of rollouts · specialist-agent memory paths.

## 8. Success criteria (phase level)

1. One sample task end-to-end on the GB10 (Harbor or declared fallback) — the spike's exit.
2. 10/10 tasks Oracle-validated before any graded rollout.
3. 60/60 rollouts logged with config hashes and retrieval logs.
4. Verdict applied in the RESULTS doc within one week of run 1 — descope executes without ceremony if triggered.
5. Coach-vs-verifier agreement table delivered (QAV calibration seed).

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Harbor/ARM64 or Docker friction on GB10 | FEAT-ABL-002 timebox + pre-declared contract-identical fallback |
| Verifier authoring cost balloons | Go/no-go after task 3 (§3.2) |
| Answer-key leakage via fixture | Per-task temporal cut + relevance spot-audit (§3.3) |
| Container ↔ host inference networking | Named build-plan item; proven in the spike |
| Nondeterminism | K=3 reps, pinned versions, config hashes |
| Coach disagrees with verifier | Not a risk — the agreement table is a deliverable |

---

**Next step:** ~~execute §2.1~~ **done 2026-07-03** (no stop condition fired; substrate home `fleet-evals` confirmed; build plan authored with FEAT-ABL-002 sequenced first as a direct session step) → **Rich reviews `phase-ablation-build-plan.md` and freezes §5 → run.** FEAT-ABL-002 does not start before that review.
