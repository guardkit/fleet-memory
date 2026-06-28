# FEAT-MEM-05 parity eval — fleet-memory vs Graphiti (2026-06-27)

**Verdict: ❌ NOT at parity. The cutover gate (FEAT-MEM-08/09) does not pass yet.**
The cause is a **fixable retrieval-pipeline defect**, not a fundamental "vector search can't
match Graphiti" — but it must be fixed and the eval re-run before cutover.

## Method

- **Probe set:** 16 queries grounded in guardkit's real read domains (architecture, decisions,
  patterns, process — the coach-context / feature-plan reads cutover must preserve).
  `eval/probe_set.json`. Scoped to **harvested-knowledge**; runtime knowledge (task_outcomes,
  failure_patterns) is out of scope (fleet-memory acquires it post-cutover via `/task-complete`).
- **fleet-memory:** `retrieval.search` + `assemble_context` over the live 447-episode / 2846-chunk
  corpus (Qwen3-Embedding-0.6B / 1024-dim), `token_budget=2000`.
- **Graphiti:** `guardkit graphiti search "<q>" -n 5` against the live FalkorDB (983 episodes).

## What we found

**1. fleet-memory returns an EMPTY context for 10 of 16 queries** (at the default 2000-token budget).
The raw vector search returns 10 hits with good scores (0.63–0.70) every time — but the assembled
context block is empty.

**2. Root cause — oversized chunks + assembly break-on-first-too-big:**
- The chunker emits **massively oversized chunks**: of 2846 chunks, **2124 (75%) exceed the
  2000-token budget**, the **average chunk is ~3000 tokens**, and the **largest is ~21,000 tokens**.
- `assemble_context` adds results in rank order and **`break`s when the first item exceeds the
  budget** (`retrieval/assembly.py`). So a single oversized top-ranked chunk → **empty context**.
  Even when non-empty, it includes at most ~1 chunk before stopping.

**3. Even at a 30k-token budget, the retrieved content is NOISE.** Oversized chunks mean a whole
(often noisy) document is one chunk, so retrieval surfaces the blob, not the relevant passage:
| query | fleet-memory top content (30k budget) |
|---|---|
| "quality gate phases" | a `QualityGateStatus(tests_passed=True, …)` object repr |
| "Player-Coach pattern" | raw `INFO:guardkit.orchestrator.autobuild:Coach provided feedback…` log lines |
| "Graphiti→fleet-memory migration" | a terminal transcript (`richardwoollcott@Richards-MBP ~ % guardkit graphiti clear…`) |

**4. Graphiti contrast — clean conceptual facts** for established concepts:
| query | Graphiti top facts |
|---|---|
| "quality gate phases" | "Phase 2.5 is a phase of Quality Gates"; "Phase 4.5 …"; "Architectural review as part of enforcement" |
| "Player-Coach pattern" | "GuardKit uses the Player-Coach Adversarial Pattern"; "… includes Coach as a component"; "CoachVerifier is a component …" |
| "complexity → review mode" | "task-review command is a review command"; "When a task is tagged 'review', its acceptance criteria …" |

> Graphiti is **not** perfect — on the recent "Graphiti→fleet-memory migration" topic it returned
> mostly irrelevant facts (it doesn't have that knowledge yet either). And Graphiti's edge here is
> precisely the **LLM extraction** fleet-memory deliberately dropped. fleet-memory's bet is that
> **good chunking + embedding retrieves the relevant clean passage** without an LLM — a bet that is
> sound in principle but **fails today** because chunks are whole documents, not passages.

## Root causes (ordered)

1. **Chunker emits oversized chunks** (`relay/chunker.py` / chunk_writer) — the primary defect.
   `chunk_target_tokens=1000` is not enforced; heading-aware sections (and RELAYBATCH01's 2048-token
   embed truncation) leave ~3000-token chunks. *This was the handoff's open finding — now quantified
   and shown to be parity-blocking.*
2. **`assemble_context` breaks on the first over-budget item** instead of skipping it (or truncating)
   — so one oversized chunk zeroes the whole context.
3. **Harvest noise** — some harvested docs are logs / terminal transcripts / status dumps. Proper
   (small) chunking mitigates this (retrieve the clean passage, not the blob); a harvest-side noise
   filter would help further.

## Fix path (then re-run this eval — it's the gate)

1. **Fix the chunker** to hard-split into ~500–1000-token, semantically coherent passages (≤ embed
   budget), so retrieval returns precise passages and no single chunk exceeds the context budget.
2. **Fix `assemble_context`** to skip (or truncate) an over-budget item and continue to fit smaller
   ones, rather than `break`. (Defensive even after chunking is fixed.)
3. *(Optional)* add a harvest-side noise filter (drop terminal transcripts / raw log captures).
4. **Re-harvest** the corpus (re-publish; the relay re-chunks + re-embeds) and **re-run this eval**
   (`eval/probe_set.json`). Only then freeze fleet-memory's answers as the regression-harness
   baselines (`probe_harness.py`) — freezing the current broken answers would be wrong.

## Caveats / scope

- **Corpus mismatch (expected, not a parity gap):** fleet-memory has only the 447 harvested **doc**
  episodes; Graphiti's 983 include runtime-captured task_outcomes/failure_patterns that fleet-memory
  gets *post-cutover*. The probe set avoids that domain.
- **Judging:** the planned LLM-judge scoring was not run — it would only quantify a fail that the
  pipeline defect already makes decisive. Re-run the judge after the chunker/assembly fix.

## Artifacts

- Probe set: `eval/probe_set.json` (reusable for the re-run)
- Capture scripts + raw outputs: session scratchpad (`capture_fleet_memory.py`, `fm_answers.json`,
  `graphiti_answers.txt`)
- Relevant code: `src/fleet_memory/relay/chunker.py`, `relay/chunk_writer.py`,
  `retrieval/assembly.py`, `retrieval/probe_harness.py`
