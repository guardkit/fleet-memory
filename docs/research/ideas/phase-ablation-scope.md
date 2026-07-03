# Memory Value Ablation — Scope (Phase ABL) — v2

**Status:** DRAFT v2 (Desktop-authored 2026-07-03). **v1 retracted same day** after review found three design holes (§1.1). §2 remains **⚠ UNVERIFIED** — Claude Code verifies from source and authors `phase-ablation-build-plan.md` before any build work.
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

## 2. Current state (⚠ UNVERIFIED — Desktop draft; verify from source before proceeding)

| Component | Believed state (2026-07-03) | Verify |
|---|---|---|
| fleet-memory core (Postgres/pgvector) | Built per phase-core | Confirm against `phase-core-build-plan.md` status |
| AutoBuild → retrieval touchpoint | Exists at context-load | **Locate exact call site; confirm whether an on/off switch exists.** If none, FEAT-ABL-001 adds one |
| Memory store contents | Unknown size/coverage | Dump stats: entry count, repos covered, timestamp range — determines fixture viability and task selection |
| Historical FEATs usable as tasks | Unknown count | Need ≥10 with: clean pre-FEAT commit, recoverable spec text, observable landed behaviour. Candidate sweep across guardkit/forge/jarvis/fleet-memory |
| Harbor on GB10 (ARM64) | Never installed | FEAT-ABL-002 spike. Harbor is a Python CLI (`pip install harbor`), likely fine; **task Docker images must be ARM64-buildable** — we author them, so controllable |
| Container → host llama-swap networking | Unknown | Rollouts run AutoBuild *inside* Docker; must reach llama-swap `:9000` on the host. Build-plan item |
| FEAT-MEM-04 / MEM-05 / fs-01 artefacts | Regression + broken harness on disk | Confirm state; these become regression tasks (§3.2) |
| GB10 capacity | 82h dataset-factory run pending go/no-go; keepalive paused | Schedule per §3.6 |

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
- **(b) Fine-tune gate evals.** Every fine-tune gets a pre-registered held-out suite on this contract *before deployment*: coach-ft-vN (code-shaped tasks), and the **incoming PO fine-tune** — doc-shaped tasks (schema validity, coverage-vs-reference build plans; PyTest handles both). **Deadline: the PO suite exists before the 82h run completes**, or its success is the next unmeasured belief.
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

**Next step:** Claude Code in `fleet-memory` (with read access to `../guardkit`, `../forge`, `../jarvis`) → execute §2.1 exactly → if no stop condition fires: confirm substrate home (`fleet-evals` recommended) and author `phase-ablation-build-plan.md` per the UBS exemplar, FEAT-ABL-002 spike sequenced first as a direct session step (no pipeline) → Rich reviews build plan and freezes §5 → run.
