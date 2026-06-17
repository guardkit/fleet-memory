/feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md


I'll orchestrate the /feature-plan workflow for "Memory Storage Substrate". First, let me load the explicit context file and check the environment.

Read storage-substrate_summary.md
Bash List feature spec directory contents
IN
ls -la /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/ 2>/dev/null; echo "---"; ls /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/ 2>/dev/null; echo "---"; ls /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/ 2>/dev/null

OUT
total 64
drwxr-xr-x  5 richardwoollcott  staff    160 Jun 12 16:21 .
drwxr-xr-x  3 richardwoollcott  staff     96 Jun 12 16:20 ..
-rw-r--r--  1 richardwoollcott  staff   5203 Jun 12 16:21 storage-substrate_assumptions.yaml
-rw-r--r--  1 richardwoollcott  staff   3006 Jun 12 16:21 storage-substrate_summary.md
-rw-r--r--  1 richardwoollcott  staff  17819 Jun 12 16:20 storage-substrate.feature
---
storage-substrate
---
docs
features
LICENSE
migrations
README.md
tasks
Bash Check Graphiti config and agentecflow scripts
IN
cat /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/graphiti.yaml 2>/dev/null || echo "NO_GRAPHITI_CONFIG"; echo "---"; ls ~/.agentecflow/bin/ 2>/dev/null | head -30

OUT
project_id: fleet_memory
enabled: true
graph_store: falkordb
falkordb_host: whitestocks
falkordb_port: 6379
timeout: 30.0
max_concurrent_episodes: 3
chunk_extraction_concurrency: 4
llm_provider: vllm
llm_base_url: http://promaxgb10-41b1:9000/v1
llm_model: qwen-graphiti
llm_max_tokens: 4096
embedding_provider: vllm
embedding_base_url: http://promaxgb10-41b1:9000/v1
embedding_model: nomic-embed
group_ids:
- product_knowledge
- command_workflows
- architecture_decisions
---
agent-enhance
agent-format
agent-validate
feature-plan-bdd-link
generate-feature-yaml
gk
gki
graphiti-check
graphiti-diagnose
guardkit
guardkit-init
Read README.md
Bash Map docs, tasks, migrations, and .guardkit directories
IN
find /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tasks /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/migrations -type f 2>/dev/null | head -40; echo "---GUARDKIT---"; find /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit -type f 2>/dev/null | head -20

OUT
/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/runbooks/RUNBOOK-nas-postgres-deploy.md
/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-build-plan.md
/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-scope.md
---GUARDKIT---
/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/graphiti.yaml
Bash Query Graphiti knowledge graph for feature planning context
IN
~/.agentecflow/bin/graphiti-check --status --task-context --quiet --description "Memory Storage Substrate: LangGraph AsyncPostgresStore on Postgres 16 + pgvector, 768-dim nomic-embed-text embeddings via llama-swap, ephemeral local deploy for tests and durable NAS deploy" --phase plan 2>&1 | head -100

OUT
{"available": true, "error": null, "context": null, "categories": 0, "tokens_used": 0, "tokens_budget": 0}
Read phase-core-build-plan.md
Read storage-substrate.feature
Bash Inspect repo root, tasks dir, and runbook header
IN
ls -la; echo "---TASKS---"; find tasks migrations -type d 2>/dev/null; echo "---PYTHON---"; ls pyproject.toml requirements.txt setup.py src tests app 2>/dev/null; echo "---CLAUDE---"; ls .claude/ 2>/dev/null; echo "---RUNBOOK HEAD---"; head -60 docs/runbooks/RUNBOOK-nas-postgres-deploy.md

OUT
total 32
drwxr-xr-x   12 richardwoollcott  staff   384 Jun 12 16:20 .
drwxr-xr-x  173 richardwoollcott  staff  5536 Jun 12 12:43 ..
drwxr-xr-x@  10 richardwoollcott  staff   320 Jun 12 13:01 .claude
drwxr-xr-x   14 richardwoollcott  staff   448 Jun 12 12:50 .git
-rw-r--r--@   1 richardwoollcott  staff  4723 Jun 12 13:02 .gitignore
drwxr-xr-x@   3 richardwoollcott  staff    96 Jun 12 12:48 .guardkit
drwxr-xr-x@   4 richardwoollcott  staff   128 Jun 12 15:28 docs
drwxr-xr-x    3 richardwoollcott  staff    96 Jun 12 16:20 features
-rw-r--r--    1 richardwoollcott  staff  1065 Jun 12 12:43 LICENSE
drwxr-xr-x@   2 richardwoollcott  staff    64 Jun 12 15:18 migrations
-rw-r--r--    1 richardwoollcott  staff    38 Jun 12 12:43 README.md
drwxr-xr-x@   7 richardwoollcott  staff   224 Jun 12 12:48 tasks
---TASKS---
tasks
migrations
tasks/completed
tasks/in_progress
tasks/backlog
tasks/in_review
tasks/blocked
---PYTHON---
---CLAUDE---
agents
CLAUDE.md
commands
hooks
manifest.json
rules
settings.json
task-plans
---RUNBOOK HEAD---
# RUNBOOK — NAS Postgres Deploy (fleet_memory durable store)

**Date:** 2026-06-12
**Status:** Ready to execute (Phase 0 manual once; Phases 1–4 scripted)
**Purpose:** Deploy Postgres 16 + pgvector to the Synology NAS as the durable fleet-memory store (FEAT-MEM-01, RD-4), fully automatable from the MacBook after one-time prep.
**Scope:** The DURABLE shared instance only. The ephemeral test instance (`deploy/local/`) is out of scope — it never touches the NAS.
**Related:** [phase-core-build-plan.md §FEAT-MEM-01](../research/ideas/phase-core-build-plan.md) — `deploy/nas/deploy.sh` is productized from the Phase 2/3 blocks below during the feature build.

---

## Credentials & secrets summary

| Item | Lives where | Notes |
|---|---|---|
| SSH **key** (`~/.ssh/fleet_memory_nas_ed25519`) | Mac keychain/agent | Auth to NAS. **Never** an SSH password in any file. |
| `deploy/nas/.env.deploy` | Mac only, `chmod 600`, gitignored (`.env*` already ignored) | `NAS_HOST`, `NAS_USER`, `NAS_SSH_PORT`, `NAS_DOCKER_ROOT`, `FLEET_MEMORY_PG_PASSWORD` |
| `.env` next to compose on NAS | NAS, `chmod 600`, rendered by deploy script | Only `POSTGRES_PASSWORD` (compose auto-loads it) |
| sudoers entry | NAS `/etc/sudoers.d/fleet_memory_deploy` | NOPASSWD for the docker binary only — not blanket sudo |

`deploy/nas/.env.deploy.example` (committed):

```bash
NAS_HOST=synology.local            # or Tailscale name/IP if the NAS runs the Tailscale package
NAS_USER=deploy_rich               # administrators-group user, key-auth only
NAS_SSH_PORT=22
NAS_DOCKER_ROOT=/volume1/docker/fleet_memory
FLEET_MEMORY_PG_PASSWORD=          # generate: openssl rand -base64 24
```

---

## Phase 0 — One-time NAS prep (manual, ~10 min, never repeated)

On DSM: **Control Panel → Terminal & SNMP → Enable SSH**. Confirm Container Manager is installed (Package Center). Then from the Mac:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/fleet_memory_nas_ed25519 -C "fleet-memory-deploy"
ssh-copy-id -i ~/.ssh/fleet_memory_nas_ed25519.pub -p 22 deploy_rich@synology.local
```

On the NAS (one interactive session, password prompts expected THIS TIME ONLY):

```bash
ssh -i ~/.ssh/fleet_memory_nas_ed25519 deploy_rich@synology.local

uname -m                                   # GATE G0a: must print x86_64
sudo -v                                    # prove admin
# Narrow NOPASSWD: docker binary only (argv[0] match covers `docker compose ...`)
echo "deploy_rich ALL=(ALL) NOPASSWD: /usr/local/bin/docker" | \
  sudo tee /etc/sudoers.d/fleet_memory_deploy
sudo chmod 440 /etc/sudoers.d/fleet_memory_deploy
mkdir -p /volume1/docker/fleet_memory/pgdata
exit
```

DSM firewall (Control Panel → Security → Firewall): allow TCP 5432 from the LAN subnet and, if the NAS is on the tailnet, `100.64.0.0/10`. Deny otherwise.

**GATE G0 (run from Mac — all three must pass before Phase 1):**

```bash
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
Now invoking the clarification-questioner agent for Context A (review scope), as the workflow requires:

Agent:Collect review scope clarifications
IN
Execute clarification for feature planning.

CONTEXT TYPE: review_scope

FEATURE: Memory Storage Substrate (FEAT-MEM-01 in the fleet-memory repo's Phase CORE build plan)

FEATURE SUMMARY: LangGraph AsyncPostgresStore on Postgres 16 + pgvector, with a 768-dimension nomic-embed-text-v1.5 embed function served by llama-swap on GB10 (:9000). Two deployment targets — deploy/local/ provides an ephemeral, random-port, throwaway instance used by ALL automated test gates (including AutoBuild), and deploy/nas/ provides the durable shared instance on the Synology NAS (backed-up volume, port 5432 exposed to LAN/Tailscale only). Covers store semantics (put/get/delete/semantic search with metadata filters), lifespan-managed connection pool, pydantic-settings profile configuration, and a three-tier test strategy (fake-embed unit tests, marker-gated integration tests against the ephemeral instance, one documented smoke against the NAS productizing runbook gates G2–G5). A BDD spec with 34 scenarios already exists at features/storage-substrate/storage-substrate.feature.

ESTIMATED COMPLEXITY: 7/10

IMPORTANT REPO FACT: The repo currently has NO Python scaffolding (no pyproject.toml, no src/, no tests/) — only GuardKit structure, docs, and the BDD spec. Scaffolding will be part of this feature.

OPEN LOW-CONFIDENCE ASSUMPTIONS (accepted as placeholders at spec time; the spec summary says they must be verified during /feature-plan):
- ASSUM-004 — Connection pool capacity is 10; operations beyond capacity queue rather than fail
- ASSUM-006 — Startup fail-fast surfaces within 10 seconds when the database is unreachable
- ASSUM-008 — Embedding calls are bounded at 10 seconds

FLAGS:
  --no-questions: false
  --with-questions: false
  --defaults: false
  --answers: (none)

IMPORTANT — EXECUTION ENVIRONMENT CONSTRAINT: You are running as a subagent and CANNOT interact with the user directly. Instead of asking questions interactively, RETURN the question set you would ask, as structured JSON, so the orchestrator can present them to the user and assemble the ClarificationContext from the answers.

Ask about (formulate these per your question protocol):
1. Review focus (all/technical/architecture/performance/security)
2. Trade-off priority (speed/quality/cost/maintainability/balanced)
3. Confirmation or revision of the three low-confidence assumption values above (since /feature-plan is the designated verification point)

Return JSON of this shape:
{
  "context_type": "review_scope",
  "questions": [
    {
      "id": "focus",
      "question": "...",
      "options": [{"key": "A", "label": "...", "description": "..."}],
      "default": "A",
      "recommended": "A",
      "rationale": "..."
    }
  ]
}

Tailor option descriptions to THIS feature (infrastructure-heavy, hermetic-testing-critical, security constraint on NAS exposure). Keep to 3 questions maximum.
Read docs
Read storage-substrate_assumptions.yaml
AskUserQuestion
OUT
Your questions have been answered: "Which aspect of FEAT-MEM-01 should the feature plan prioritise in its analysis?"="All areas (Recommended)", "When the plan must trade off between competing goals, which takes precedence?"="Hermetic correctness (Recommended)", "Three low-confidence spec assumptions need values before tasks can be sized: ASSUM-004 pool capacity (10, excess queues), ASSUM-006 startup fail-fast (within 10s), ASSUM-008 embed timeout (10s). How should the plan treat them?"="Defaults + verify (Recommended)". You can now continue with these answers in mind.
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
task-create skill
Task-create instructions loaded. Generating the hash-based task ID and creating the review task file:

Bash Generate hash-based review task ID
IN
python3 -c "
import hashlib, time
h = hashlib.sha256(f'Plan: Memory Storage Substrate{time.time()}'.encode()).hexdigest()[:4].upper()
print(f'TASK-REV-{h}')
"

OUT
TASK-REV-CA81
Write TASK-REV-CA81-plan-memory-storage-substrate.md
75 lines
---
id: TASK-REV-CA81
title: "Plan: Memory Storage Substrate"
status: backlog
created: 2026-06-12T16:30:00Z
updated: 2026-06-12T16:30:00Z
priority: high
task_type: review
tags: [feature-planning, storage, pgvector, infrastructure, hermetic-testing]
complexity: 7
review_mode: decision
review_depth: standard
context_files:
  - features/storage-substrate/storage-substrate_summary.md
  - features/storage-substrate/storage-substrate.feature
  - features/storage-substrate/storage-substrate_assumptions.yaml
  - docs/research/ideas/phase-core-build-plan.md
  - docs/runbooks/RUNBOOK-nas-postgres-deploy.md
clarification:
  context_a:
    timestamp: 2026-06-12T16:29:00Z
    decisions:
      focus: all
      tradeoff: hermetic_correctness
      assumptions: defaults_plus_verify
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Plan: Memory Storage Substrate

## Description

Decision-mode review for FEAT-MEM-01 (Phase CORE build plan): the storage substrate
for fleet-memory. LangGraph `AsyncPostgresStore` on Postgres 16 + pgvector with a
768-dimension nomic-embed-text-v1.5 embed function served by llama-swap on GB10
(:9000). Two deployment targets — `deploy/local/` (ephemeral, random-port, throwaway
instance used by ALL automated test gates including AutoBuild) and `deploy/nas/`
(durable shared instance on the Synology NAS; backed-up volume, 5432 LAN/Tailscale
only). Store semantics (put/get/delete/semantic search with metadata filters),
lifespan-managed connection pool, pydantic-settings profile configuration, and the
three-tier test strategy (fake-embed unit tests, marker-gated integration tests
against the ephemeral instance, one documented smoke against the NAS productizing
runbook gates G2–G5).

The BDD spec already exists: 34 scenarios at `features/storage-substrate/storage-substrate.feature`.

## Review Scope (Context A clarification)

- **Focus**: All areas — balanced coverage across hermetic test infrastructure,
  store semantics, lifespan/pool wiring, settings profiles, NAS security boundary,
  and scaffolding (repo currently has NO Python scaffolding).
- **Trade-off priority**: Hermetic correctness — deploy/local isolation provably
  right (random ports, parallel-worktree safety, aborted-run cleanup). The AC makes
  this the explicit pass/fail gate: full suite passes with the NAS powered off.
- **Low-confidence assumptions** (ASSUM-004 pool=10/queue, ASSUM-006 fail-fast 10s,
  ASSUM-008 embed timeout 10s): use as defaults; implementation verifies against
  asyncpg-pool/httpx/AsyncPostgresStore actuals and may revise with recorded
  reasoning — no spec amendment needed.

## Acceptance Criteria (from build plan FEAT-MEM-01)

- [ ] `store.aput` / `asearch` round-trip with real nomic embeddings against the ephemeral instance
- [ ] Full test suite passes on the MacBook with the NAS powered off (hermeticity proven)
- [ ] NAS instance deployed via the runbook's scripted path (`deploy.sh`); `smoke.sh` (G2–G5) passes from the Mac
- [ ] Vector index created at 768 dims; search returns by similarity with metadata filter
- [ ] No hyphens in any Postgres identifier; namespace tuples use underscores
- [ ] Connection pool opens/closes cleanly under lifespan; settings via env only

## Review Findings

[Populated by /task-review]
✅ Task created: TASK-REV-CA81 — tasks/backlog/TASK-REV-CA81-plan-memory-storage-substrate.md

Now executing the decision review:

Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
task-review skill
Agent:Decision review FEAT-MEM-01 substrate
IN
You are performing a DECISION-MODE feature-planning review (TASK-REV-CA81) for FEAT-MEM-01 "Memory Storage Substrate" in the fleet-memory repo at /Users/richardwoollcott/Projects/appmilla_github/fleet-memory. Your final message is consumed by an orchestrator (not shown to a human directly) — return the full structured analysis described at the end.

READ THESE FILES FIRST (they are the authoritative context):
1. /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate_summary.md
2. /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate.feature (34 BDD scenarios)
3. /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate_assumptions.yaml
4. /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-build-plan.md (§FEAT-MEM-01, architectural constraints, RD-1..8)
5. /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/runbooks/RUNBOOK-nas-postgres-deploy.md (full runbook — gates G0–G6, Phases 0–4)

REVIEW SCOPE (Context A clarification from user):
- Focus: ALL areas (hermetic test infra, store semantics, lifespan/pool wiring, settings profiles, NAS security boundary, scaffolding)
- Trade-off priority: HERMETIC CORRECTNESS above speed/maintainability — the AC "full test suite passes with the NAS powered off; AutoBuild must never depend on the NAS" is the explicit pass/fail gate
- Low-confidence assumptions ASSUM-004 (pool=10, queue not fail), ASSUM-006 (startup fail-fast ≤10s), ASSUM-008 (embed timeout 10s): treat as DEFAULTS; implementation verifies against asyncpg/httpx/AsyncPostgresStore actuals and may revise with recorded reasoning

KEY REPO FACTS (verified):
- The repo has NO Python scaffolding: no pyproject.toml, no src/, no tests/. Only .claude/ (GuardKit), docs/, features/, migrations/ (empty), tasks/ (empty kanban dirs), LICENSE, README.
- CLAUDE.md declares the nats-asyncio-service template idiom: FastStream + Pydantic + pydantic-settings, layered (Schemas/Handlers/Services), handler→service unidirectional, lifespan-managed resources, TestNatsBroker for handler tests. FEAT-MEM-01 itself needs NO NATS — the relay consumer arrives in FEAT-MEM-04. Decide how much app shell to scaffold now.
- Identifiers must use underscores everywhere (no hyphens) — package fleet_memory, Postgres objects, namespace tuples.
- nomic-embed-text-v1.5 (768 dims) is served at llama-swap on GB10 :9000, OpenAI-compatible /v1/embeddings, reachable from the Mac over Tailscale. Always-on.
- LangGraph AsyncPostgresStore comes from the langgraph-checkpoint-postgres package (langgraph.store.postgres.aio.AsyncPostgresStore); index config {dims, embed, fields}; store.setup() creates its schema but pgvector extension must exist (CREATE EXTENSION vector).
- The NAS runbook is complete and scripted (Phases 1–4 with gates G0–G6); deploy/nas/deploy.sh + smoke.sh are to be PRODUCTIZED from runbook Phases 2–3. Phase 0 (SSH key, sudoers, firewall) is one-time manual operator work, ALREADY documented.

ANALYZE THESE DECISION AXES (this is decision mode — give 2–3 options each for the axes that genuinely have alternatives, with a clear recommendation):
1. Ephemeral test Postgres provisioning for hermetic gates: docker compose file in deploy/local/ with random host port via env + pytest fixture orchestration, vs testcontainers-python, vs raw docker run in a fixture. Weigh: parallel-worktree isolation (two simultaneous runs must not conflict), aborted-run cleanup (no orphan containers/data), AutoBuild compatibility, the BDD scenarios "Parallel test runs each get their own isolated ephemeral instance" / "An aborted test run still leaves no trace behind" / "An explicitly requested integration run fails clearly when no ephemeral instance can start", and the build-plan statement that deploy/local/ is a compose file.
2. Embed function design: plain async httpx callable (build plan says httpx against OpenAI-compatible /v1/embeddings) vs openai-python client vs langchain embeddings class. Must support: fake/injectable for unit tests, dimension validation (768 exact, loud failure on mismatch), bounded timeout (default 10s), no partial writes on embed failure.
3. App shell / lifespan integration: minimal FastStream app shell now (template idiom, lifespan wires pool+store, no subscribers) vs plain asyncio entrypoint with contextlib.AsyncExitStack vs defer app shell entirely and expose only a store factory + async context manager. Consider FEAT-MEM-02/03/04 will build on this.
4. Settings/profiles: single pydantic-settings class with FLEET_MEMORY_ env prefix + .env.example documenting mac-dev vs test profiles (build plan names FLEET_MEMORY_PG_DSN, FLEET_MEMORY_EMBED_URL, FLEET_MEMORY_EMBED_MODEL). Decide pool-size/timeout settings fields for the three placeholder assumptions.
5. pgvector enablement: docker-entrypoint-initdb.d init SQL in both composes vs migrations/ SQL applied by a script vs store.setup()-adjacent code. migrations/ dir already exists (empty).

THEN PRODUCE THE IMPLEMENTATION BREAKDOWN — subtasks sized for autonomous implementation (AutoBuild Player/Coach), respecting:
- A scaffolding task must come first (pyproject.toml with pinned core deps, src/fleet_memory/ package, tests/ layout with unit/ and integration/ split, pytest config with integration marker excluded by default, ruff config). Underscore naming.
- Hermeticity tasks: deploy/local/ compose + conftest fixtures (session-scoped ephemeral instance, random port, cleanup-on-abort, parallel-safe project names), fake embed fixture for unit tier.
- Store core: settings class, embed callable, store factory/lifecycle context manager, lifespan wiring into app shell.
- deploy/nas/ AUTHORING (compose, .env.deploy.example, deploy.sh, smoke.sh productized from runbook Phases 2–3 with gates G2–G5 inline) is automatable file authoring; the actual NAS DEPLOYMENT + smoke EXECUTION against the live NAS is operator work (live infrastructure — AutoBuild cannot and must not reach the NAS) and must be a SEPARATE task flagged operator_handoff.
- Tests: unit tier (fake embed, no network — store semantics via ephemeral pg? NO: unit tier has NO database either, per scenario "Unit tests pass with no database and no embedding service available" — design what unit tests cover: settings validation, embed callable with mocked transport, dimension validation, namespace validation) and integration tier (marker-gated, ephemeral Postgres + real nomic over Tailscale: round-trip, ranked search, metadata filter, upsert/delete, pool lifecycle, concurrent writes, limit boundaries).
- Each task: id-suffix-style name, task_type (scaffolding|feature|testing|documentation|infrastructure|declarative|operator_handoff), complexity 1–10, dependencies, primary files it creates/touches, estimated_minutes, 3–6 verifiable acceptance criteria (file_exists/command-runs/test-passes shaped — avoid prose like "works correctly"), and which BDD scenario titles it covers.
- Identify wave structure: which tasks can run in parallel (no file conflicts), which are sequential.
- Map ASSUM-004/006/008 verification into the relevant tasks' acceptance criteria (verify-and-record, values may be revised).

RETURN (markdown, these exact section headings):
## Executive Summary
## Technical Options Analysis  (per decision axis: options with pros/cons/complexity, ★ recommendation + rationale)
## Recommended Approach        (one coherent paragraph + bullet decisions)
## Implementation Breakdown    (per task: name, task_type, complexity, deps, est_minutes, files, acceptance criteria, BDD scenarios covered)
## Wave Structure              (wave → task list, rationale re file conflicts)
## Risks
## Effort & Complexity Summary (total complexity 1-10, total estimated hours)
## Open Items For Implementation (the three assumptions + anything discovered)
Read storage-substrate_assumptions.yaml
Read phase-core-build-plan.md
Read RUNBOOK-nas-postgres-deploy.md
The architect's analysis is complete (54.9KB). Reading the full output:

Bash Extract architect analysis to temp file
IN
python3 -c "
import json
with open('/Users/richardwoollcott/.claude/projects/-Users-richardwoollcott-Projects-appmilla-github-fleet-memory/1e9796e2-b0b2-428e-9269-04718afdff32/tool-results/toolu_01WmtDErGtSw9eLnqtqt3sMZ.json') as f:
    data = json.load(f)
text = data[0]['text']
print(text)
" > /tmp/review-analysis.md; wc -l /tmp/review-analysis.md

OUT
     557 /tmp/review-analysis.md
Read review-analysis.md
Bash Write review report to .claude/reviews/
IN
mkdir -p /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.claude/reviews && { cat <<'HEADER'
# Review Report: TASK-REV-CA81 — Plan: Memory Storage Substrate (FEAT-MEM-01)

## Review Details
- **Mode**: Decision Analysis
- **Depth**: Standard
- **Date**: 2026-06-12
- **Reviewer**: software-architect agent
- **Context A**: focus=all, trade-off=hermetic correctness, assumptions=defaults+verify (ASSUM-004/006/008)
- **Graphiti context**: none available (new project knowledge graph)
- **Context sources**: storage-substrate_summary.md, storage-substrate.feature (34 scenarios), storage-substrate_assumptions.yaml, phase-core-build-plan.md, RUNBOOK-nas-postgres-deploy.md

HEADER
tail -n +3 /tmp/review-analysis.md; } > /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.claude/reviews/TASK-REV-CA81-review-report.md
wc -l /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.claude/reviews/TASK-REV-CA81-review-report.md

OUT
     566 /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.claude/reviews/TASK-REV-CA81-review-report.md
Edit TASK-REV-CA81-plan-memory-storage-substrate.md
Added 8 lines
Bash Move review task to in_review state
IN
mv /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tasks/backlog/TASK-REV-CA81-plan-memory-storage-substrate.md /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tasks/in_review/

OUT
(Bash completed with no output)
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
AskUserQuestion
OUT
Your questions have been answered: "The decision review for "Memory Storage Substrate" is complete: 13 tasks across 8 waves, recommended approach settled on all 5 decision axes. What would you like to do?"="[I]mplement". You can now continue with these answers in mind.
User chose [I]mplement. 13 subtasks ≥ 2, so Context B (implementation preferences) applies — invoking the clarification-questioner agent:

Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
Agent:Collect implementation preferences
IN
Execute clarification for implementation.

CONTEXT TYPE: implementation_prefs

REVIEW FINDINGS (TASK-REV-CA81 — FEAT-MEM-01 Memory Storage Substrate, fleet-memory repo):
  Recommended approach (single coherent bundle, all 5 decision axes resolved):
    - Docker Compose deploy/local/ + UUID-project pytest fixtures for ephemeral Postgres
    - Plain async httpx embed callable with injectable fake, 768-dim guard
    - Minimal FastStream app shell with lifespan-wired AsyncPostgresStore, no subscribers
    - Single FLEET_MEMORY_ pydantic-settings class with assumption placeholders as defaults
    - pgvector via initdb/01_extensions.sql in both composes
  Alternative options per axis exist (testcontainers, openai client, plain-asyncio entrypoint) but each lost clearly on the hermetic-correctness trade-off the user already chose.
  Subtask count: 13 (1 scaffolding, 4 feature, 1 infrastructure, 1 declarative, 4 testing, 1 documentation, 1 operator_handoff)
  Wave structure: 8 waves; waves 2, 3, 6, 7 have 2-task parallelism; rest sequential
  Estimated: ~10.5h AutoBuild, ~6.5-7h critical path
  Target executor: GuardKit /feature-build (AutoBuild Player/Coach), possibly Conductor worktrees for parallel waves

FLAGS:
  --no-questions: false
  --with-questions: false
  --defaults: false
  --answers: (none)

EXECUTION ENVIRONMENT CONSTRAINT: You are a subagent and CANNOT interact with the user. RETURN the questions you would ask as structured JSON (same shape as Context A: {"context_type": "implementation_prefs", "questions": [{id, question, options:[{key,label,description}], default, recommended, rationale}]}) so the orchestrator can present them.

Ask about (3 questions max):
1. Approach selection — confirm the recommended bundle vs revisit a specific axis
2. Execution preference — parallel execution (Conductor/feature-build concurrency for the 2-task waves) vs sequential vs auto-detect
3. Testing depth — TDD / standard quality gates / minimal — noting that 4 of 13 tasks ARE test-suite tasks and the BDD spec with 34 scenarios already exists (R2 BDD oracle will run tagged scenarios)

Tailor descriptions to THIS feature. Be concise.
Read features
AskUserQuestion
OUT
Your questions have been answered: "Confirm the recommended implementation bundle for the storage substrate, or flag an axis to revisit?"="Confirm bundle (Recommended)", "How should the 13-task / 8-wave plan be executed (waves 2, 3, 6, 7 have 2-task parallelism)?"="Auto-detect (Recommended)", "What testing depth for the subtasks? (34 BDD scenarios already exist; 4 of 13 tasks are dedicated test-suite tasks.)"="Standard gates (Recommended)", "⚠️ OPERATOR_HANDOFF DETECTED — the "NAS deploy execution" task's ACs are runtime observations AutoBuild cannot satisfy: "deploy.sh runs against the live Synology NAS, Gate G2 passes", "smoke.sh Gates G3–G5 pass from the Mac", "after a DSM reboot G2/G4 re-pass". Strong signals: live infrastructure (NAS, LAN/Tailscale), human verbs (operator runs), reboot observation. Mark it task_type: operator_handoff so AutoBuild skips it?"="Yes — operator_handoff (Recommended)". You can now continue with these answers in mind.
Bash Check generate-feature-yaml flags and TaskType enum values
IN
python3 ~/.agentecflow/bin/generate-feature-yaml --help 2>&1 | head -50; echo "===TASKTYPE==="; python3 -c "
from guardkit.orchestrator.feature_loader import TaskType
print([t.value for t in TaskType])
" 2>/dev/null || grep -rn "class TaskType" ~/.agentecflow/ 2>/dev/null | head -5 || pip3 show guardkit 2>/dev/null | head -3

OUT
/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages/langchain_core/_api/deprecation.py:25: UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.
  from pydantic.v1.fields import FieldInfo as FieldInfoV1
usage: generate-feature-yaml [-h] [--name NAME] [--description DESCRIPTION]
                             [--task TASKS] [--tasks-json TASKS_JSON]
                             [--base-path BASE_PATH] [--feature-id FEATURE_ID]
                             [--output OUTPUT] [--json] [--quiet]
                             [--feature-slug FEATURE_SLUG]
                             [--task-base-path TASK_BASE_PATH] [--strict]
                             [--lenient] [--discover]
                             [--auto-serialise-overlap]
                             [--validate-smoke-gates]

Generate structured YAML feature files for AutoBuild

options:
  -h, --help            show this help message and exit
  --name, -n NAME       Feature name (required for generation; ignored by
                        --validate-smoke-gates)
  --description, -d DESCRIPTION
                        Feature description
  --task, -t TASKS      Task in format ID:NAME:COMPLEXITY:DEPS (can be
                        repeated)
  --tasks-json TASKS_JSON
                        JSON file or string containing tasks array
  --base-path, -p BASE_PATH
                        Base path for project (default: current directory)
  --feature-id FEATURE_ID
                        Override auto-generated feature ID
  --output, -o OUTPUT   Override output path (default:
                        .guardkit/features/FEAT-XXX.yaml)
  --json                Output JSON format instead of YAML
  --quiet, -q           Suppress progress output
  --feature-slug FEATURE_SLUG
                        Feature slug for deriving task file paths (e.g.,
                        'dark-mode', 'oauth2')
  --task-base-path TASK_BASE_PATH
                        Base path for task files (default: tasks/backlog)
  --strict              Make path validation errors fatal (default: True). Use
                        --lenient to override.
  --lenient             Make path validation errors non-fatal (overrides
                        --strict default).
  --discover            Discover actual task files on disk instead of deriving
                        paths from names. Globs for {task_id}*.md in the
                        feature directory.
  --auto-serialise-overlap
                        When tasks within a parallel-execution wave appear to
                        edit overlapping files (inferred from task
                        descriptions and ACs), split the offending wave into a
                        sequential follow-on entry instead of warning.
                        Default: warn-only. See TASK-FIX-A7B3.
===TASKTYPE===
['scaffolding', 'feature', 'infrastructure', 'integration', 'documentation', 'testing', 'refactor', 'declarative', 'operator_handoff']
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
Write TASK-MEM-001-scaffold-project-layout.md
63 lines
---
id: TASK-MEM-001
title: Scaffold project layout
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: scaffolding
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 1
implementation_mode: direct
complexity: 3
estimated_minutes: 40
dependencies: []
tags: [scaffolding, pyproject, pytest, ruff]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Scaffold project layout

## Description

Establish the Python project skeleton for fleet_memory. The repo currently has NO
Python scaffolding — only GuardKit structure, docs, and the BDD spec. Create
`pyproject.toml` with pinned core dependencies, the `src/fleet_memory/` package,
the `tests/unit/` + `tests/integration/` split, pytest configuration with the
`integration` marker excluded by default, and ruff configuration. All identifiers
use underscores (no hyphens anywhere — FalkorDB scar tissue).

Note: `AsyncPostgresStore` is provided by `langgraph-checkpoint-postgres`, which
uses psycopg3 + psycopg-pool (NOT asyncpg). DSNs are plain `postgresql://`
conninfo strings.

## Acceptance Criteria

- [ ] `pyproject.toml` exists with `[project]` `name = "fleet_memory"`, requires-python `>=3.12`, and pinned deps: `faststream[nats]`, `pydantic>=2`, `pydantic-settings>=2`, `langgraph-checkpoint-postgres>=2.0`, `httpx`, `psycopg[binary]`, `psycopg-pool`; dev extras: `pytest`, `pytest-asyncio`, `pytest-timeout`, `ruff`, `pyyaml`
- [ ] `pip install -e ".[dev]"` succeeds and `python -c "import fleet_memory"` exits 0
- [ ] `python -c "from langgraph.store.postgres.aio import AsyncPostgresStore"` exits 0 (confirms the pinned package exposes the store API — review risk R5)
- [ ] `tests/unit/test_scaffold.py` contains `test_package_imports` (imports `fleet_memory`); `python -m pytest tests/ -q` exits 0 with 1 passed — the `integration` marker is excluded by default via `addopts = -m "not integration"` and registered in pytest config
- [ ] `ruff check src/ tests/` exits 0
- [ ] No filename or Python identifier under `src/` or `tests/` contains a hyphen

## Test Requirements

- [ ] `tests/unit/test_scaffold.py::test_package_imports` passes
- [ ] Default pytest run collects zero `integration`-marked tests

## BDD Scenarios Covered

- "Unit tests pass with no database and no embedding service available" (structural prerequisite — marker exclusion)
- "An explicitly requested integration run fails clearly when no ephemeral instance can start" (marker gating established here)

## Implementation Notes

- Layout: `src/fleet_memory/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `pytest.ini` (or `[tool.pytest.ini_options]` in pyproject), `ruff.toml` (or `[tool.ruff]`)
- pytest config must set `asyncio_mode = "auto"` (pytest-asyncio) and register the `integration` marker so `--strict-markers` is viable later
- `.gitignore` already covers `.env*` — extend only if venv/cache patterns are missing
- The placeholder unit test gives every later wave's smoke gate a non-empty, passing `tests/unit` collection from Wave 1 onward
Write TASK-MEM-002-settings-class-env-profiles.md
59 lines
---
id: TASK-MEM-002
title: Settings class and env profiles
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: declarative
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 2
implementation_mode: direct
complexity: 3
estimated_minutes: 35
dependencies: [TASK-MEM-001]
tags: [pydantic-settings, configuration, assumptions]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Settings class and env profiles

## Description

Single pydantic-settings `Settings` class with `env_prefix = "FLEET_MEMORY_"` and
`.env` file support, plus a committed `.env.example` documenting the `mac-dev`
(durable NAS target over LAN/Tailscale) and `test` (ephemeral target) profiles.
The three low-confidence assumption placeholders become documented field defaults:
ASSUM-004 → `pg_pool_max=10`, ASSUM-006 → `pg_connect_timeout_s=10.0`,
ASSUM-008 → `embed_timeout_s=10.0`. A production/GB10 profile is deferred to
FEAT-MEM-04 (OD-5) — note this in `.env.example` comments.

## Acceptance Criteria

- [ ] `src/fleet_memory/settings.py` exports `Settings` with fields: `pg_dsn` (required), `embed_url` (required), `embed_model: str = "nomic-embed-text-v1.5"`, `embed_dims: int = 768`, `embed_timeout_s: float = 10.0`, `pg_pool_min: int = 2`, `pg_pool_max: int = 10`, `pg_connect_timeout_s: float = 10.0`, `nats_url: str = "nats://localhost:4222"`; verified by `python -c "from fleet_memory.settings import Settings; s = Settings(FLEET_MEMORY_PG_DSN='postgresql://u:p@localhost/db', FLEET_MEMORY_EMBED_URL='http://localhost:9000'); assert s.pg_pool_max == 10 and s.embed_timeout_s == 10.0 and s.pg_connect_timeout_s == 10.0"` exiting 0
- [ ] `python -c "from fleet_memory.settings import Settings; Settings()"` with no `FLEET_MEMORY_` env raises `ValidationError` whose message names each missing field
- [ ] `.env.example` exists with clearly labelled `mac-dev` and `test` blocks, documents every `FLEET_MEMORY_` field, uses plain `postgresql://` DSN format (psycopg3 conninfo — no `+asyncpg` suffix), and carries inline comments marking `pg_pool_max` / `pg_connect_timeout_s` / `embed_timeout_s` as ASSUM-004/006/008 placeholders pending verification (TASK-MEM-013)
- [ ] `python -m pytest tests/unit/test_settings.py -v` passes covering: missing-field error names each field, all defaults match the documented placeholders, `FLEET_MEMORY_` prefix isolation (unprefixed `PG_DSN` env is ignored), and OS env vars take precedence over `.env` file values (review risk R6)
- [ ] Empty-string `FLEET_MEMORY_PG_DSN` or `FLEET_MEMORY_EMBED_URL` raises `ValidationError`
- [ ] `settings.py` imports no NATS, no httpx, no psycopg — pure pydantic-settings
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_settings.py` — hermetic (no network, no database)

## BDD Scenarios Covered

- "Configuration profiles select the correct deployment target from the environment"
- "Missing required settings prevent startup with a clear message"

## Implementation Notes

- `model_config = SettingsConfigDict(env_prefix="FLEET_MEMORY_", env_file=".env", env_file_encoding="utf-8")`
- pydantic-settings v2 gives env vars precedence over `.env` by default — assert it explicitly so a stray operator `.env` pointing at the NAS can never hijack the test tier
- Keep DSN type permissive enough for both `postgresql://` and unix-socket forms; validate non-empty
Write TASK-MEM-003-embed-callable-dimension-guard.md
70 lines
---
id: TASK-MEM-003
title: Embed callable with dimension guard
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: feature
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 3
implementation_mode: task-work
complexity: 4
estimated_minutes: 45
dependencies: [TASK-MEM-002]
tags: [embeddings, httpx, nomic, timeout]
consumer_context:
  - task: TASK-MEM-002
    consumes: FLEET_MEMORY_SETTINGS
    framework: "httpx async client against OpenAI-compatible /v1/embeddings (llama-swap)"
    driver: "httpx"
    format_note: "embed_url is the base URL of the OpenAI-compatible API (e.g. http://gb10:9000/v1 or host root — normalise to .../v1/embeddings); embed_timeout_s is the httpx read-timeout bound in seconds (ASSUM-008 placeholder 10.0)"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Embed callable with dimension guard

## Description

Plain async httpx embed function against the OpenAI-compatible `/v1/embeddings`
endpoint served by llama-swap on GB10 (:9000). Signature:
`async def embed(texts: list[str], settings: Settings) -> list[list[float]]`
(or a `make_embed(settings)` factory returning the closed-over callable that
`AsyncPostgresStore` index config accepts). Post-call dimension validation: any
vector whose length differs from `settings.embed_dims` (768) raises
`EmbedDimensionError` — loud failure, never silent truncation. Timeout bounded by
`settings.embed_timeout_s` (ASSUM-008 default 10.0). Includes
`make_fake_embed(dims=768)` factory for the unit tier.

## Acceptance Criteria

- [ ] `python -m pytest tests/unit/test_embed.py -v` passes with zero network calls (httpx `MockTransport` throughout)
- [ ] Dimension-mismatch rows 512, 767, 769, 1024 each raise `EmbedDimensionError` whose message names both actual and expected dimensions (BDD `@boundary @negative` outline)
- [ ] A `MockTransport` that never responds triggers `EmbedTimeoutError` within `embed_timeout_s` — ASSUM-008 verification: record the actual httpx connect-vs-read timeout semantics observed, in a comment in `test_embed.py`
- [ ] `src/fleet_memory/embed.py` exports the async embed callable (settings-driven) and `make_fake_embed(dims=768)` returning a deterministic, network-free callable
- [ ] `src/fleet_memory/errors.py` exports `EmbedDimensionError`, `EmbedTimeoutError`, `EmbedServiceError`; error messages may name the embedding service URL but never any database credential
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_embed.py` — `MockTransport` only; no socket opened
- [ ] Failure-mode coverage: HTTP 500 → `EmbedServiceError`; malformed JSON → `EmbedServiceError`; timeout → `EmbedTimeoutError`; wrong dims → `EmbedDimensionError`

## BDD Scenarios Covered

- "An embedding of exactly 768 dimensions is stored and searchable" (callable side)
- "An embedding with the wrong number of dimensions is rejected" (all 4 outline rows)
- "A hung embedding service cannot stall store operations indefinitely"
- "Database credentials never appear in logs or error messages" (embed-side)

## Implementation Notes

- `httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=settings.embed_timeout_s, write=5.0, pool=5.0))` — the ASSUM-008 bound applies to the read phase (model inference time), confirm and record
- OpenAI-compatible request body: `{"model": settings.embed_model, "input": texts}`; response `data[i].embedding`
- The callable must be directly usable as the `embed` field of `AsyncPostgresStore` index config (TASK-MEM-005 consumes it) — keep the public shape `async (list[str]) -> list[list[float]]` via factory closure over settings
- Fake: `make_fake_embed(768)` returns deterministic unit-norm vectors derived from a text hash so ranking tests are stable
Write TASK-MEM-004-local-ephemeral-compose-fixtures.md
68 lines
---
id: TASK-MEM-004
title: Local ephemeral compose and pytest fixtures
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: infrastructure
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 2
implementation_mode: task-work
complexity: 5
estimated_minutes: 60
dependencies: [TASK-MEM-001]
tags: [docker-compose, pgvector, hermetic-testing, fixtures]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Local ephemeral compose and pytest fixtures

## Description

The hermeticity backbone: `deploy/local/docker-compose.yml` providing the
ephemeral, random-port, throwaway Postgres 16 + pgvector instance used by ALL
automated test gates (including AutoBuild), plus the pytest fixtures that
orchestrate it. Each test session mints a UUID-seeded compose project name
(`fleet_memory_test_<uid>`) and a random host port, registers `atexit` cleanup so
aborted runs leave no trace, and skips fast with a clear diagnostic when Docker is
absent. Parallel worktrees each get their own conflict-free instance.
**AutoBuild must never depend on the NAS.**

## Acceptance Criteria

- [ ] `deploy/local/docker-compose.yml` exists: image `pgvector/pgvector:pg16`, host port env-overridable (no fixed 5432 binding; fixture assigns a free random port), mounts `./initdb` to `/docker-entrypoint-initdb.d`, defines a `pg_isready` healthcheck with `interval: 2s`, `retries: 10` (review risk R4 — the fixture waits on health, not the port)
- [ ] `deploy/local/initdb/01_extensions.sql` contains `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] With Docker unavailable, an explicit `python -m pytest tests/integration/ -m integration` run fails/skips quickly (no hang) with a message naming Docker / the container runtime as the missing prerequisite
- [ ] The session-scoped `ephemeral_pg` fixture yields a plain `postgresql://` DSN at `127.0.0.1` on a non-5432 random port; after session teardown `docker compose -p <project> ps -q` is empty and the anonymous volume is removed (`down -v`) — verified by a minimal integration self-test
- [ ] After fixture startup, `SELECT extname FROM pg_extension` includes `vector` (init script ran on the fresh volume — review risk R3)
- [ ] Two fixture instantiations with distinct project uids yield DSNs on different ports with mutually invisible data (parallel-isolation self-test)
- [ ] `tests/conftest.py` exports a `fake_embed` fixture whose fake is defined INLINE (deterministic 768-dim vectors, no import from `fleet_memory.embed` — that module lands in a later wave); using it alone opens no database or network connection
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] A marker-gated self-test (`tests/integration/test_ephemeral_fixture.py`) exercising fixture startup, pgvector presence, random port, teardown emptiness
- [ ] `atexit`-registered `docker compose -p <project> down -v` covers SIGINT/aborted runs

## BDD Scenarios Covered

- "An ephemeral test instance provides a fresh database for a test run"
- "Parallel test runs each get their own isolated ephemeral instance"
- "An aborted test run still leaves no trace behind"
- "An explicitly requested integration run fails clearly when no ephemeral instance can start"
- "The full test suite passes with the durable shared instance powered off" (foundation)
- "Unit tests pass with no database and no embedding service available" (fake_embed fixture)

## Implementation Notes

- Project name: `fleet_memory_test_{uuid4().hex[:8]}` — underscores only
- Random port: bind a socket to port 0, read the assigned port, release, pass as `PGPORT` env to compose (small race window is acceptable; compose fails loudly on collision and the fixture may retry once)
- Teardown order: `request.addfinalizer` for normal exit; `atexit.register` as the abort net; both idempotent
- DSN shape: `postgresql://fleet_memory:fleet_memory@127.0.0.1:{port}/fleet_memory` — credentials are test-only constants in the compose file, never reused for the NAS
- Keep `tests/integration/conftest.py` self-contained: reads env, shells to `docker compose`; does NOT import `fleet_memory.settings`
Write TASK-MEM-005-store-factory-namespace-validation.md
110 lines
---
id: TASK-MEM-005
title: Store factory and namespace validation
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: feature
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 4
implementation_mode: task-work
complexity: 5
estimated_minutes: 55
dependencies: [TASK-MEM-002, TASK-MEM-003]
tags: [langgraph, asyncpostgresstore, pgvector, namespaces]
consumer_context:
  - task: TASK-MEM-002
    consumes: FLEET_MEMORY_PG_DSN
    framework: "langgraph AsyncPostgresStore (langgraph-checkpoint-postgres)"
    driver: "psycopg3 + psycopg-pool"
    format_note: "Plain postgresql://user:pass@host:port/dbname conninfo — psycopg3 format, NO +asyncpg dialect suffix; pool sizing from pg_pool_min/pg_pool_max, connect bound from pg_connect_timeout_s"
  - task: TASK-MEM-003
    consumes: EMBED_CALLABLE
    framework: "AsyncPostgresStore index config"
    driver: "httpx (inside the callable)"
    format_note: "async callable list[str] -> list[list[float]], exactly settings.embed_dims (768) floats per vector; raises EmbedDimensionError/EmbedTimeoutError/EmbedServiceError on failure"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Store factory and namespace validation

## Description

`src/fleet_memory/store.py`: an `asynccontextmanager` `async_store_context(settings,
embed_fn=None)` that yields a configured `AsyncPostgresStore` with index config
`{"dims": settings.embed_dims, "embed": <callable>, "fields": ["content"]}`, plus
`validate_namespace()` enforcing underscores-only identifiers at validation time —
before anything reaches the database. When `embed_fn` is None the real httpx
callable is constructed from settings; tests inject fakes.

## Acceptance Criteria

- [ ] `src/fleet_memory/store.py` exports `async_store_context(settings, embed_fn=None)` as an asynccontextmanager yielding `AsyncPostgresStore`; entering it runs `store.setup()`; exiting closes the pool cleanly
- [ ] `validate_namespace(("fleet_memory", "my-project", "chunk"))` raises `NamespaceValidationError` whose message states identifiers must use underscores; `validate_namespace(("fleet_memory", "fleet_memory", "adr"))` passes — enforcement happens before any database call
- [ ] `python -m pytest tests/unit/test_store_validation.py -v` passes with no database and no network (the factory is constructed but never entered in the unit tier)
- [ ] `grep -rE "import psycopg|from psycopg|import asyncpg" tests/unit/` exits non-zero (no direct driver imports in unit tests — hermeticity of the unit tier)
- [ ] Driver/API verification recorded (review risk R5): confirm against the installed `langgraph-checkpoint-postgres` version that (a) the conninfo is plain `postgresql://` psycopg3 format, (b) the index-config key shape `{dims, embed, fields}` matches the constructor signature, (c) pool min/max from settings flow into the actual pool — record findings as comments in `store.py`
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_store_validation.py` — namespace acceptance/rejection table, factory construction with `make_fake_embed`, no `__aenter__` in unit tier

## BDD Scenarios Covered

- "A namespace containing hyphens is rejected"
- "Storing a memory and retrieving it by its key" (factory prerequisite)
- "The connection pool lives and dies with the service" (context-manager shape)

## Implementation Notes

- `from langgraph.store.postgres.aio import AsyncPostgresStore`; prefer `AsyncPostgresStore.from_conn_string(...)` or explicit pool construction — whichever the pinned version documents for pool-size + timeout control
- Pass `settings.pg_connect_timeout_s` into pool/connection acquisition so ASSUM-006 has a real lever
- Namespace rule: every tuple element matches `^[a-z0-9_]+$`
- Credential hygiene: any exception raised out of the context manager must not interpolate the DSN password (strip/passwordless repr)

## Seam Tests

The following seam test validates the integration contracts with TASK-MEM-002 (DSN format) and TASK-MEM-003 (embed callable). Implement it to verify the boundary before integration.

```python
"""Seam test: verify FLEET_MEMORY_PG_DSN and EMBED_CALLABLE contracts."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("FLEET_MEMORY_PG_DSN")
def test_pg_dsn_format_is_psycopg3_conninfo():
    """Verify the DSN is plain postgresql:// psycopg3 conninfo.

    Contract: plain postgresql:// — NO +asyncpg dialect suffix (psycopg3 driver).
    Producer: TASK-MEM-002
    """
    from fleet_memory.settings import Settings
    s = Settings(FLEET_MEMORY_PG_DSN="postgresql://u:p@localhost:5499/db",
                 FLEET_MEMORY_EMBED_URL="http://localhost:9000")
    dsn = str(s.pg_dsn)
    assert dsn.startswith("postgresql://"), f"Expected plain postgresql:// conninfo, got: {dsn}"
    assert "+asyncpg" not in dsn, f"psycopg3 conninfo must not carry +asyncpg suffix: {dsn}"


@pytest.mark.seam
@pytest.mark.integration_contract("EMBED_CALLABLE")
async def test_embed_callable_returns_768_dim_vectors():
    """Verify the embed callable contract consumed by the store index config.

    Contract: async list[str] -> list[list[float]], exactly 768 floats per vector.
    Producer: TASK-MEM-003
    """
    from fleet_memory.embed import make_fake_embed
    embed = make_fake_embed(768)
    vectors = await embed(["one text", "two text"])
    assert len(vectors) == 2
    assert all(len(v) == 768 for v in vectors), "Every vector must be exactly 768 dims"
```
Write TASK-MEM-006-app-shell-lifespan.md
89 lines
---
id: TASK-MEM-006
title: App shell with lifespan-managed store
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: feature
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 5
implementation_mode: task-work
complexity: 4
estimated_minutes: 45
dependencies: [TASK-MEM-003, TASK-MEM-005]
tags: [faststream, lifespan, app-shell]
consumer_context:
  - task: TASK-MEM-005
    consumes: STORE_CONTEXT
    framework: "FastStream lifespan context manager"
    driver: "langgraph AsyncPostgresStore via async_store_context"
    format_note: "asynccontextmanager yielding a ready AsyncPostgresStore (setup() already run); entering connects + verifies, exiting releases every connection"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: App shell with lifespan-managed store

## Description

Minimal FastStream app shell per the nats-asyncio-service template idiom:
module-level `broker = NatsBroker(settings.nats_url)`, `FastStream(broker)` app
with a lifespan that enters `async_store_context` and exposes the store to future
handlers. NO subscribers yet — FEAT-MEM-04 slots its MEMORY-stream consumer into
this shell without restructuring. Startup against an unreachable database fails
fast with a diagnostic naming the target (ASSUM-006), and the layer boundary holds:
store/embed/settings modules contain zero NATS imports.

## Acceptance Criteria

- [ ] `src/fleet_memory/app.py` exports module-level `broker` and a `FastStream` app whose lifespan enters `async_store_context(settings)` and exposes the store (app/broker context attribute); no `@broker.subscriber` present; `python -c "from fleet_memory.app import app, broker"` exits 0 with required `FLEET_MEMORY_` env set
- [ ] Lifespan unit test using `TestNatsBroker` enters and exits cleanly with a fake embed and a mocked/stubbed store context — no real NATS, no real Postgres
- [ ] Startup-failure unit test: with a DSN pointing at a closed local port and the REAL store context, lifespan entry raises within `pg_connect_timeout_s` plus slack (test wall-clock under 15 s) and the error names the database target without leaking the password — ASSUM-006 verification: record the actual observed driver timeout behaviour in a test comment
- [ ] `grep -rE "from nats|import nats|faststream" src/fleet_memory/store.py src/fleet_memory/embed.py src/fleet_memory/settings.py` exits non-zero (service layers carry zero broker imports — handler/service boundary)
- [ ] `python -m pytest tests/unit/test_app_lifespan.py -v` passes
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] `tests/unit/test_app_lifespan.py` — TestNatsBroker pattern; no network beyond the deliberately-refused localhost port in the failure test

## BDD Scenarios Covered

- "The connection pool lives and dies with the service"
- "The service refuses to start when the database is unreachable"
- "Missing required settings prevent startup with a clear message" (entry point surfaces Settings ValidationError)

## Implementation Notes

- Settings construction happens inside app assembly (factory function) so import-time side effects stay minimal and tests can inject env
- `nats_url` has a benign default; no NATS connection is attempted during unit tests (TestNatsBroker patches it)
- Fail-fast diagnostic format: name host + database, never the password (credential-hygiene scenario)

## Seam Tests

```python
"""Seam test: verify STORE_CONTEXT contract from TASK-MEM-005."""
import pytest


@pytest.mark.seam
@pytest.mark.integration_contract("STORE_CONTEXT")
async def test_store_context_yields_ready_store(monkeypatch):
    """Verify async_store_context is an asynccontextmanager yielding a store.

    Contract: entering runs setup() and yields a ready AsyncPostgresStore;
    exiting releases connections. Unit tier verifies the SHAPE with a stub.
    Producer: TASK-MEM-005
    """
    import contextlib
    from fleet_memory import store as store_mod
    assert hasattr(store_mod, "async_store_context")
    cm = store_mod.async_store_context  # must be usable as: async with cm(settings, embed_fn) as s:
    assert callable(cm)
    # Shape check only in unit tier — wave-6 integration tests enter it for real.
```
Write TASK-MEM-007-nas-deploy-files.md
60 lines
---
id: TASK-MEM-007
title: NAS deploy files (compose, deploy.sh, smoke.sh)
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: infrastructure
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 3
implementation_mode: task-work
complexity: 4
estimated_minutes: 50
dependencies: [TASK-MEM-004]
tags: [nas, synology, deployment, runbook-productization]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: NAS deploy files (compose, deploy.sh, smoke.sh)

## Description

AUTHOR (do not execute against the NAS) the durable-instance deployment artifacts
in `deploy/nas/`, productized from `docs/runbooks/RUNBOOK-nas-postgres-deploy.md`
Phases 2–3 with gates G2–G5 inline. This task creates files and validates their
syntax locally; the actual deployment to the live Synology NAS is TASK-MEM-008
(operator handoff). Mirrors the `deploy/local/` conventions (same image, same
`initdb/` pattern) so there is ONE NAS-container convention.

## Acceptance Criteria

- [ ] `deploy/nas/docker-compose.yml` exists: image `pgvector/pgvector:pg16`, service `fleet_memory_postgres`, `restart: unless-stopped`, bind mount `${NAS_DOCKER_ROOT}/pgdata:/var/lib/postgresql/data`, port `5432:5432`, `env_file: .env` (compose auto-loads `POSTGRES_PASSWORD`), mounts `./initdb` to `/docker-entrypoint-initdb.d`; comments document the DSM firewall expectation (LAN + tailnet `100.64.0.0/10` only)
- [ ] `deploy/nas/initdb/01_extensions.sql` contains `CREATE EXTENSION IF NOT EXISTS vector;` (same content as deploy/local — runbook gate G3 baked into the container)
- [ ] `deploy/nas/deploy.sh` is executable, `set -euo pipefail`, sources `.env.deploy`, performs rsync + remote `.env` render + `docker compose up -d` exactly per runbook Phases 2–3, carries gate G2 inline with PASS/FAIL echo labels, contains no `sshpass` and no plaintext password literal
- [ ] `deploy/nas/smoke.sh` is executable, carries gates G3 (pg_isready over SSH), G4 (`psql` over the LAN/Tailscale DSN returns 1), G5 (`pgdata/PG_VERSION` reads 16 on the backed-up share) inline with PASS/FAIL labels, and exits non-zero on any gate failure
- [ ] `deploy/nas/.env.deploy.example` is committed with the five runbook fields (`NAS_HOST`, `NAS_USER`, `NAS_SSH_PORT`, `NAS_DOCKER_ROOT`, `FLEET_MEMORY_PG_PASSWORD`) empty-valued, with the `openssl rand -base64 24` generation comment; `.env.deploy` itself is covered by the existing `.env*` gitignore rule (verify)
- [ ] `bash -n deploy/nas/deploy.sh && bash -n deploy/nas/smoke.sh` exits 0 (syntax check; run shellcheck too if available)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] Syntax-level only (`bash -n`, optional shellcheck) — NO network calls, NO SSH, NO NAS contact in this task or its Coach validation

## BDD Scenarios Covered

- "The documented smoke check verifies the shared instance end-to-end" (file authoring; execution in TASK-MEM-008)
- "Memories on the durable shared instance survive a restart" (`restart: unless-stopped` + bind-mount on backed-up share)
- "The durable shared instance refuses connections from outside the private network" (firewall documentation + compose comments)

## Implementation Notes

- Source of truth: RUNBOOK-nas-postgres-deploy.md — keep gate numbering (G2–G5) and PASS/FAIL output format identical to the runbook blocks so operator muscle memory transfers
- SSH invocation shape: `ssh -i ~/.ssh/fleet_memory_nas_ed25519 -p $NAS_SSH_PORT $NAS_USER@$NAS_HOST` with `sudo /usr/local/bin/docker` (the narrow NOPASSWD sudoers entry)
- Underscores in every Postgres identifier (database `fleet_memory`, user `fleet_memory`)
- Do NOT add these scripts to any automated test gate — they are operator tools
Write TASK-MEM-008-nas-deploy-operator-execution.md
57 lines
---
id: TASK-MEM-008
title: NAS deploy execution and smoke (operator)
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: operator_handoff
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 8
implementation_mode: direct
complexity: 1
estimated_minutes: 30
dependencies: [TASK-MEM-007]
tags: [nas, synology, operator, live-infrastructure]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: NAS deploy execution and smoke (operator)

## Description

Deploy the durable shared Postgres instance to the live Synology NAS using the
scripted path authored in TASK-MEM-007, and verify it with the documented smoke
gates. This is live-infrastructure, human-in-the-loop work: AutoBuild must never
reach the NAS (the hermeticity acceptance criterion depends on it), so this task
is `operator_handoff` by design — confirmed by the operator at plan time.

## Required operator follow-up

This task is `task_type: operator_handoff` — AutoBuild will not attempt it. The
operator must verify the runtime acceptance criteria below manually, then mark
the task complete via `/task-complete`.

- **AC-1**: Phase 0 one-time NAS prep done (SSH key, narrow-docker sudoers, DSM firewall LAN+tailnet rule) and Gate **G0** passes from the Mac (`uname -m` → x86_64; key-auth SSH; NOPASSWD docker)
- **AC-2**: `deploy/nas/deploy.sh` runs from the Mac and Gate **G2** passes (container `fleet_memory_postgres` is `Up` on the NAS)
- **AC-3**: `deploy/nas/smoke.sh` runs from the Mac and Gates **G3, G4, G5** all PASS — G3: `pg_isready` over SSH; G4: `psql` over the LAN/Tailscale DSN returns `1` (the same network path the service will use); G5: `${NAS_DOCKER_ROOT}/pgdata/PG_VERSION` reads `16` (data on the backed-up share)
- **AC-4**: Gate **G6** — after a DSM reboot, G2 and G4 re-pass without manual intervention (`restart: unless-stopped` proven)
- **AC-5**: Port 5432 is reachable from LAN/tailnet only; a connection attempt from outside is refused (DSM firewall rule verified)

## BDD Scenarios Covered

- "The documented smoke check verifies the shared instance end-to-end"
- "Memories on the durable shared instance survive a restart"
- "The durable shared instance refuses connections from outside the private network"

## Implementation Notes

- Runbook: docs/runbooks/RUNBOOK-nas-postgres-deploy.md (Phases 0–4, gates G0–G6)
- Estimated operator wall-clock: 30–45 min including the one-time Phase 0
- Credentials: `deploy/nas/.env.deploy` (Mac-only, chmod 600, gitignored); generate `FLEET_MEMORY_PG_PASSWORD` via `openssl rand -base64 24`
- After completion, the `mac-dev` profile (`.env`) can point `FLEET_MEMORY_PG_DSN` at the NAS for development reads/writes
Write TASK-MEM-009-unit-test-suite.md
62 lines
---
id: TASK-MEM-009
title: Unit test suite completion (hermetic tier)
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 6
implementation_mode: task-work
complexity: 4
estimated_minutes: 60
dependencies: [TASK-MEM-003, TASK-MEM-005, TASK-MEM-006]
tags: [unit-tests, hermetic, credential-hygiene]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Unit test suite completion (hermetic tier)

## Description

Complete the network-free, database-free unit tier. Earlier tasks created focused
test stubs (`test_embed.py`, `test_store_validation.py`, `test_app_lifespan.py`,
`test_settings.py`); this task expands them into the full hermetic suite and adds
`test_credential_hygiene.py`. The tier's contract: `FLEET_MEMORY_PG_DSN` and
`FLEET_MEMORY_EMBED_URL` are NOT set in the environment, no socket is opened, and
the whole tier finishes in seconds — proving the BDD scenario "Unit tests pass
with no database and no embedding service available".

## Acceptance Criteria

- [ ] `python -m pytest tests/unit/ -v --timeout=30` passes with `FLEET_MEMORY_PG_DSN` and `FLEET_MEMORY_EMBED_URL` unset (hermetic by construction)
- [ ] `test_credential_hygiene.py`: when the embed callable raises `EmbedServiceError` and when `async_store_context` fails on a bad DSN, no propagated message contains the password component of the DSN
- [ ] Settings `ValidationError` from empty env names the missing `pg_dsn` / `embed_url` fields (message includes each missing setting's name)
- [ ] Suite covers: settings defaults + precedence, namespace hyphen rejection, all four dimension-mismatch rows, embed timeout, fake-embed store-factory construction, lifespan enter/exit with stubs
- [ ] Total wall-clock for `python -m pytest tests/unit/ -q` is under 10 seconds (network-free proof — no blocking call hides in the tier)
- [ ] Tests do not import psycopg directly and never call `async_store_context().__aenter__` against a real DSN

## Test Requirements

- [ ] All unit tests pass; the tier alone satisfies the default `pytest` invocation (integration excluded by marker)

## BDD Scenarios Covered

- "Unit tests pass with no database and no embedding service available"
- "Missing required settings prevent startup with a clear message"
- "Database credentials never appear in logs or error messages"
- "A namespace containing hyphens is rejected"
- "An embedding with the wrong number of dimensions is rejected"
- "A hung embedding service cannot stall store operations indefinitely"

## Implementation Notes

- Use `monkeypatch.delenv` to guarantee env emptiness regardless of the developer's shell
- Credential-hygiene assertion helper: extract the password from the test DSN, assert `password not in str(exc)` across every captured failure path
- Keep per-test fixtures function-scoped; the tier must stay order-independent
Write TASK-MEM-010-integration-store-semantics.md
97 lines
---
id: TASK-MEM-010
title: "Integration tests: store semantics and pool lifecycle"
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 6
implementation_mode: task-work
complexity: 6
estimated_minutes: 90
dependencies: [TASK-MEM-004, TASK-MEM-005, TASK-MEM-006]
tags: [integration-tests, marker-gated, pool, semantics]
consumer_context:
  - task: TASK-MEM-004
    consumes: EPHEMERAL_PG_DSN
    framework: "pytest session fixture (ephemeral_pg)"
    driver: "docker compose + psycopg3"
    format_note: "Plain postgresql:// DSN at 127.0.0.1 on a random non-5432 port; throwaway data; NEVER the NAS host"
  - task: TASK-MEM-005
    consumes: STORE_CONTEXT
    framework: "langgraph AsyncPostgresStore"
    driver: "psycopg3 + psycopg-pool"
    format_note: "async_store_context(settings, embed_fn) yields a ready store; setup() idempotent"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Integration tests — store semantics and pool lifecycle

## Description

Marker-gated (`@pytest.mark.integration`) tests against the ephemeral Postgres
instance with REAL nomic embeddings from GB10 llama-swap (:9000) over Tailscale.
Covers the core store semantics (round-trip, upsert, delete, ranked semantic
search) and the pool lifecycle, including the ASSUM-004 and ASSUM-006
verifications with record-and-revise semantics. The NAS is never referenced.

## Acceptance Criteria

- [ ] `python -m pytest tests/integration/ -m integration -v --timeout=120` passes against the ephemeral instance; no test references any NAS DSN
- [ ] Round-trip: `aput` then `aget` returns byte-identical content with `created_at`/`updated_at` present
- [ ] Upsert: two `aput` calls to the same key leave exactly one record; `aget` returns the second version only; delete: after `adelete`, both `aget` and `asearch` return nothing for the key
- [ ] Ranking: with memories about "database connection pooling" and "holiday rota planning" stored, `asearch("how do we manage Postgres connections")` ranks the pooling memory first and every result carries a relevance score (real nomic round-trip proven)
- [ ] Pool lifecycle: enter → `aput` → exit leaks no connection (`pg_stat_activity` count restored); `store.setup()` run twice is idempotent; ASSUM-006: actual observed connect-timeout against a closed port recorded in a test comment
- [ ] Pool pressure (ASSUM-004): 15 concurrent `aput` calls against `pg_pool_max=10` — record the actual psycopg-pool behaviour: if operations queue and all 15 complete within a 30 s bound the assumption holds; if the pool raises a timeout error instead, capture it, adjust the test to assert the actual contract, and flag the revised value for TASK-MEM-013

## Test Requirements

- [ ] Files: `tests/integration/test_store_round_trip.py`, `test_store_semantics.py`, `test_pool_lifecycle.py`
- [ ] Requires: Docker running, Tailscale route to GB10 — documented in module docstrings; the default (non-integration) run never executes these

## BDD Scenarios Covered

- "Storing a memory and retrieving it by its key"
- "Storing to an existing key replaces the previous memory"
- "Deleting a memory removes it from retrieval and search"
- "Semantic search returns memories ranked by relevance to the query"
- "The connection pool lives and dies with the service"
- "Operations beyond pool capacity queue rather than fail"
- "The full test suite passes with the durable shared instance powered off"

## Implementation Notes

- Build `Settings` for the test from the `ephemeral_pg` fixture DSN + the real GB10 embed URL (env-provided, e.g. `FLEET_MEMORY_EMBED_URL` in the developer's shell or a test-tier `.env` block)
- Namespace per test: `("fleet_memory", "test_<uuid>", "memory")` — isolation inside the shared session instance
- pg_stat_activity comparison must filter to the test database name to avoid flakiness

## Seam Tests

```python
"""Seam test: verify EPHEMERAL_PG_DSN contract from TASK-MEM-004."""
import pytest


@pytest.mark.seam
@pytest.mark.integration
@pytest.mark.integration_contract("EPHEMERAL_PG_DSN")
def test_ephemeral_dsn_is_local_random_port(ephemeral_pg):
    """Verify the fixture DSN targets localhost on a random, non-NAS port.

    Contract: plain postgresql:// at 127.0.0.1, port != 5432, never the NAS.
    Producer: TASK-MEM-004
    """
    dsn = ephemeral_pg
    assert dsn.startswith("postgresql://"), f"Expected plain postgresql:// conninfo, got: {dsn}"
    assert "127.0.0.1" in dsn or "localhost" in dsn, f"Ephemeral instance must be local: {dsn}"
    assert ":5432/" not in dsn, "Ephemeral instance must not squat the default Postgres port"
    for forbidden in ("synology", "nas", "100.64."):
        assert forbidden not in dsn.lower(), f"NAS reference leaked into ephemeral DSN: {dsn}"
```
Write TASK-MEM-011-integration-boundaries-embed-failures.md
65 lines
---
id: TASK-MEM-011
title: "Integration tests: search boundaries and embed failures"
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 7
implementation_mode: task-work
complexity: 5
estimated_minutes: 70
dependencies: [TASK-MEM-010]
tags: [integration-tests, boundaries, negative-cases]
consumer_context:
  - task: TASK-MEM-004
    consumes: EPHEMERAL_PG_DSN
    framework: "pytest session fixture (ephemeral_pg) — seam owned by TASK-MEM-010"
    driver: "docker compose + psycopg3"
    format_note: "Inherits the fixture contract proven by TASK-MEM-010's seam test; same conftest, no new seam stub required"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Integration tests — search boundaries and embed failures

## Description

Marker-gated integration tests for the boundary and negative scenarios: search
limit semantics (exactly-N, default cap), empty-store search, embed-service-down
atomicity (no partial writes), and hostile-content inertness. Uses the same
ephemeral fixture and store context as TASK-MEM-010.

## Acceptance Criteria

- [ ] Limit boundaries: with 15 relevant memories stored, `asearch(query, limit=N)` returns exactly N for N ∈ {1, 10, 15}, best-ranked first
- [ ] Default limit (ASSUM-002): `asearch(query)` with no limit returns at most 10 results — record the actual `AsyncPostgresStore` default; if it differs from 10, record the observed value for TASK-MEM-013 and assert the actual contract
- [ ] Empty store: `asearch("anything at all")` against a fresh namespace succeeds with zero results and no error
- [ ] Embed-down atomicity (ASSUM-005): with an injected always-failing embed callable, `aput` of a searchable memory raises an error identifying the embedding service AND a subsequent `aget` for that key returns nothing (no partial record); previously stored memories remain retrievable
- [ ] Hostile content: a memory containing SQL-injection-shaped text (e.g. `'; DROP TABLE memories; --`) round-trips byte-identical via `aput`/`aget`, appears normally in search, and no other memory or store structure is affected
- [ ] Dimension mismatch at the store boundary: a wrong-dims embed callable causes the write to fail with the dimension-mismatch error and leaves no partial record

## Test Requirements

- [ ] Files: `tests/integration/test_search_boundaries.py`, `test_embed_failures.py`, `test_injection_safety.py`
- [ ] All `@pytest.mark.integration`; excluded from the default run

## BDD Scenarios Covered

- "Search returns no more results than the requested limit" (all 3 outline rows)
- "Search without an explicit limit returns at most the default number of results"
- "Searching an empty store returns no results without error"
- "Storing a searchable memory fails cleanly when the embedding service is down"
- "Hostile memory content is stored verbatim and stays inert"

## Implementation Notes

- The failing-embed injection reuses `async_store_context(settings, embed_fn=failing_embed)` — no monkeypatching of internals
- Hostile-content equality must be byte-level (`stored == retrieved` on the raw value), not post-normalisation
- Fresh namespace per test for isolation within the session-scoped instance
Write TASK-MEM-012-integration-metadata-concurrency.md
65 lines
---
id: TASK-MEM-012
title: "Integration tests: metadata filters and concurrency"
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: testing
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 7
implementation_mode: task-work
complexity: 5
estimated_minutes: 60
dependencies: [TASK-MEM-010]
tags: [integration-tests, metadata-filter, concurrency, mvcc]
consumer_context:
  - task: TASK-MEM-004
    consumes: EPHEMERAL_PG_DSN
    framework: "pytest session fixture (ephemeral_pg) — seam owned by TASK-MEM-010"
    driver: "docker compose + psycopg3"
    format_note: "Inherits the fixture contract proven by TASK-MEM-010's seam test; same conftest, no new seam stub required"
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Integration tests — metadata filters and concurrency

## Description

Marker-gated integration tests for filtered semantic search and concurrent-access
semantics: project-scoped metadata filtering with preserved ranking, concurrent
same-key writes converging on one complete winner, and reads never observing a
partial write (Postgres MVCC). Closes the integration tier with a full-suite green
run and a hermeticity grep.

## Acceptance Criteria

- [ ] Metadata filter: memories from `project_a` and `project_b`, both relevant to the query; `asearch` filtered to `project_a` returns only `project_a` memories, still ranked by relevance with scores present
- [ ] Concurrent same-key writes (ASSUM-003): `asyncio.gather` of two `aput` calls with different content to one key — afterwards `aget` returns exactly one of the two versions in full; never a blend or partial
- [ ] Read-during-write (ASSUM-013): a reader polling `asearch`/`aget` while a writer rewrites the same key only ever observes the complete old or complete new version
- [ ] Full integration tier green: `python -m pytest tests/integration/ -m integration -v --timeout=120` passes (Tasks 010 + 011 + 012 files together)
- [ ] Hermeticity grep: `grep -riE "synology|nas_host|100\.64\." tests/integration/` exits non-zero (no NAS references anywhere in the integration tier)
- [ ] Fixture parallel-isolation re-check: the suite passes when run twice concurrently from two shells (distinct compose projects, distinct ports — documented as a manual-or-CI check in the module docstring if not automated)

## Test Requirements

- [ ] Files: `tests/integration/test_metadata_filter.py`, `test_concurrent_writes.py`
- [ ] All `@pytest.mark.integration`

## BDD Scenarios Covered

- "Semantic search can be constrained by metadata filters"
- "Concurrent writes to the same key leave one complete winner"
- "A search during a concurrent write never sees a partial memory"
- "Parallel test runs each get their own isolated ephemeral instance" (re-verified at suite level)

## Implementation Notes

- Filter mechanism: store values carry a `project` field; `asearch(namespace_prefix, query=..., filter={"project": "project_a"})` — confirm the exact filter parameter shape against the pinned langgraph-checkpoint-postgres version
- The read-during-write loop needs a bounded duration (e.g. 50 iterations) to stay deterministic in CI
- Use distinct content lengths for the two concurrent versions so a blend would be detectable by length alone
Write TASK-MEM-013-assumption-verification-record.md
56 lines
---
id: TASK-MEM-013
title: Assumption verification record
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: documentation
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 8
implementation_mode: direct
complexity: 1
estimated_minutes: 20
dependencies: [TASK-MEM-009, TASK-MEM-010, TASK-MEM-011, TASK-MEM-012]
tags: [assumptions, documentation, verification]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: Assumption verification record

## Description

Close the loop on the three low-confidence spec assumptions (Context A decision:
defaults + verify). The test tasks measured the actual behaviour; this task
records the verified values in `storage-substrate_assumptions.yaml` and aligns
`settings.py` defaults if any verified value differs from its placeholder.

## Acceptance Criteria

- [ ] ASSUM-004 entry updated with a `verified_value` field recording the actual psycopg-pool overflow behaviour observed in TASK-MEM-010 (queue vs timeout, and at what bound)
- [ ] ASSUM-006 entry updated with `verified_value` recording the actual connect-timeout behaviour observed in TASK-MEM-006/010 against a closed port
- [ ] ASSUM-008 entry updated with `verified_value` recording the actual httpx read-timeout behaviour observed in TASK-MEM-003
- [ ] Each updated entry: `confidence` changed from `low` to `verified`, plus a `verified_by_task` field naming the measuring task
- [ ] If any verified value differs from its placeholder (10 / 10s / 10s), the corresponding `settings.py` default and `.env.example` comment are updated in the same commit, with the reasoning recorded in the assumption entry
- [ ] `python -c "import yaml; d = yaml.safe_load(open('features/storage-substrate/storage-substrate_assumptions.yaml')); assert all(a.get('confidence') != 'low' for a in d['assumptions'])"` exits 0
- [ ] If TASK-MEM-011 found a non-10 default search limit (ASSUM-002), record it the same way

## Test Requirements

- [ ] None beyond the YAML sanity check — this is a documentation task

## BDD Scenarios Covered

- "Operations beyond pool capacity queue rather than fail" (ASSUM-004 recorded)
- "The service refuses to start when the database is unreachable" (ASSUM-006 recorded)
- "A hung embedding service cannot stall store operations indefinitely" (ASSUM-008 recorded)

## Implementation Notes

- Source measurements from the test-file comments the earlier tasks were required to leave (TASK-MEM-003 AC3, TASK-MEM-006 AC3, TASK-MEM-010 AC5/AC6, TASK-MEM-011 AC2)
- Spec-amendment-free by design: Context A chose "defaults + verify", so revisions here need recorded reasoning, not a new spec round
Write IMPLEMENTATION-GUIDE.md
194 lines
# Implementation Guide: Memory Storage Substrate (FEAT-CA81 / FEAT-MEM-01)

**Parent review**: TASK-REV-CA81 ([report](../../../.claude/reviews/TASK-REV-CA81-review-report.md))
**BDD spec**: features/storage-substrate/storage-substrate.feature (34 scenarios)
**Trade-off priority** (Context A): hermetic correctness — the full suite passes with the NAS powered off; AutoBuild never touches the NAS.
**Approach** (Context B confirmed): deploy/local compose + UUID-project pytest fixtures · plain httpx embed callable with injectable fake · minimal FastStream shell with lifespan-wired `AsyncPostgresStore` · single `FLEET_MEMORY_` settings class · pgvector via `initdb/01_extensions.sql`.

## Data Flow: Read/Write Paths

```mermaid
flowchart LR
    subgraph Writes["Write Paths"]
        W1["store.aput()\nvia async_store_context\n(TASK-MEM-005)"]
        W2["embed callable → llama-swap :9000\n/v1/embeddings (TASK-MEM-003)"]
        W3["deploy.sh → NAS schema/init\n(TASK-MEM-007/008)"]
    end

    subgraph Storage["Storage"]
        S1[("ephemeral Postgres\npgvector :random_port\n(throwaway, per-run)")]
        S2[("NAS Postgres\npgvector :5432\n(durable, backed-up)")]
    end

    subgraph Reads["Read Paths"]
        R1["aget / asearch\nintegration tests\n(TASK-MEM-010/011/012)"]
        R2["smoke.sh G4\npsql SELECT 1 (operator)"]
        R3["production retrieval\n(FEAT-MEM-05)"]
    end

    W2 -->|"768-dim vectors"| W1
    W1 -->|"test profile DSN"| S1
    W3 -->|"operator-only"| S2

    S1 -->|"same store context"| R1
    S2 -->|"LAN/Tailscale"| R2
    S2 -.->|"NOT WIRED (deferred)"| R3

    style R3 fill:#fcc,stroke:#c00
    style S1 fill:#cfc,stroke:#090
```

_Look for: every automated write/read stays on the ephemeral instance (green); the NAS is written only by the operator path and read only by the operator smoke gate._

**Disconnection Alert**: 1 read path has no caller in this feature. The NAS durable
instance has no production reader/writer inside FEAT-MEM-01 — by design. Production
writes arrive with FEAT-MEM-03/04 (writer + relay consumer) and production reads
with FEAT-MEM-05 (retrieval API); the `mac-dev` profile in `.env.example`
(TASK-MEM-002) is the bridge that will point the service at the NAS. **Deferral
acknowledged at the [I]mplement checkpoint — tracked here, no wiring task added.**

## Integration Contracts (sequence)

```mermaid
sequenceDiagram
    participant App as FastStream lifespan (006)
    participant Set as Settings (002)
    participant Store as async_store_context (005)
    participant Embed as embed callable (003)
    participant LS as llama-swap :9000
    participant PG as ephemeral Postgres (004)

    App->>Set: Settings() from FLEET_MEMORY_ env
    Set-->>App: pg_dsn, embed_url, pool + timeout bounds
    App->>Store: async with async_store_context(settings)
    Store->>PG: connect (pool min/max, connect_timeout_s)
    Store->>PG: store.setup() (idempotent)
    Store-->>App: ready AsyncPostgresStore

    Note over App,PG: write path
    App->>Store: aput(namespace, key, value)
    Store->>Embed: embed([content]) — bounded by embed_timeout_s
    Embed->>LS: POST /v1/embeddings
    LS-->>Embed: 768-dim vectors (else EmbedDimensionError)
    Store->>PG: upsert row + vector

    Note over App,PG: read path
    App->>Store: asearch(query, filter)
    Store->>Embed: embed([query])
    Store->>PG: vector similarity + metadata filter
    PG-->>App: ranked results with scores

    Note over Store,PG: on embed failure: no partial write reaches PG (ASSUM-005)
```

_Look for: embeddings are fetched and passed onward into the same `aput` call — no fetch-then-discard point exists; an embed failure aborts the write before Postgres sees it._

## Task Dependencies

```mermaid
graph TD
    T1[TASK-MEM-001 Scaffold] --> T2[TASK-MEM-002 Settings]
    T1 --> T4[TASK-MEM-004 Ephemeral compose+fixtures]
    T2 --> T3[TASK-MEM-003 Embed callable]
    T4 --> T7[TASK-MEM-007 NAS deploy files]
    T2 --> T5[TASK-MEM-005 Store factory]
    T3 --> T5
    T3 --> T6[TASK-MEM-006 App shell lifespan]
    T5 --> T6
    T3 --> T9[TASK-MEM-009 Unit suite]
    T5 --> T9
    T6 --> T9
    T4 --> T10[TASK-MEM-010 Integration: semantics+pool]
    T5 --> T10
    T6 --> T10
    T10 --> T11[TASK-MEM-011 Integration: boundaries]
    T10 --> T12[TASK-MEM-012 Integration: metadata+concurrency]
    T7 --> T8[TASK-MEM-008 NAS deploy ⚠ operator]
    T9 --> T13[TASK-MEM-013 Assumption record]
    T10 --> T13
    T11 --> T13
    T12 --> T13

    style T2 fill:#cfc,stroke:#090
    style T4 fill:#cfc,stroke:#090
    style T3 fill:#cfc,stroke:#090
    style T7 fill:#cfc,stroke:#090
    style T9 fill:#cfc,stroke:#090
    style T10 fill:#cfc,stroke:#090
    style T11 fill:#cfc,stroke:#090
    style T12 fill:#cfc,stroke:#090
    style T8 fill:#ffe9a8,stroke:#b8860b
```

_Tasks with green background run in parallel within their wave; amber = operator_handoff (AutoBuild skips it)._

## §4: Integration Contracts

### Contract: FLEET_MEMORY_PG_DSN
- **Producer task:** TASK-MEM-002 (Settings class)
- **Consumer task(s):** TASK-MEM-005 (store factory), TASK-MEM-006 (lifespan)
- **Artifact type:** environment variable / Settings field
- **Format constraint:** Plain `postgresql://user:pass@host:port/dbname` conninfo — psycopg3 format required by langgraph `AsyncPostgresStore` (langgraph-checkpoint-postgres uses psycopg3 + psycopg-pool). **NO `+asyncpg` dialect suffix.**
- **Validation method:** Coach runs TASK-MEM-005's seam test `test_pg_dsn_format_is_psycopg3_conninfo`; `.env.example` shows the plain format

### Contract: EMBED_CALLABLE
- **Producer task:** TASK-MEM-003 (embed callable)
- **Consumer task(s):** TASK-MEM-005 (store index config)
- **Artifact type:** Python async callable
- **Format constraint:** `async (list[str]) -> list[list[float]]`, exactly `settings.embed_dims` (768) floats per vector; raises `EmbedDimensionError` / `EmbedTimeoutError` / `EmbedServiceError` — never returns malformed vectors
- **Validation method:** Coach runs TASK-MEM-005's seam test `test_embed_callable_returns_768_dim_vectors`; dimension-mismatch unit rows in TASK-MEM-003

### Contract: STORE_CONTEXT
- **Producer task:** TASK-MEM-005 (store factory)
- **Consumer task(s):** TASK-MEM-006 (lifespan), TASK-MEM-010 (integration tier)
- **Artifact type:** asynccontextmanager
- **Format constraint:** `async_store_context(settings, embed_fn=None)` yields a ready `AsyncPostgresStore` (setup() already run, idempotent); exit releases every connection
- **Validation method:** TASK-MEM-006 seam shape-test; TASK-MEM-010 pool-lifecycle test (pg_stat_activity before/after)

### Contract: EPHEMERAL_PG_DSN
- **Producer task:** TASK-MEM-004 (ephemeral compose + fixtures)
- **Consumer task(s):** TASK-MEM-010 (seam owner); TASK-MEM-011/012 inherit via the shared conftest fixture
- **Artifact type:** pytest session fixture yielding a DSN string
- **Format constraint:** plain `postgresql://` at `127.0.0.1` on a random non-5432 port; data throwaway per session; never references the NAS host
- **Validation method:** Coach runs TASK-MEM-010's seam test `test_ephemeral_dsn_is_local_random_port`; TASK-MEM-012's hermeticity grep

## Execution Strategy

| Wave | Tasks | Parallel? |
|---|---|---|
| 1 | TASK-MEM-001 scaffold | — |
| 2 | TASK-MEM-002 settings ∥ TASK-MEM-004 ephemeral compose | ⚡ 2-way (disjoint trees: `src/` vs `deploy/local/`+`tests/conftest`) |
| 3 | TASK-MEM-003 embed ∥ TASK-MEM-007 NAS files | ⚡ 2-way (`src/fleet_memory/embed.py` vs `deploy/nas/`) |
| 4 | TASK-MEM-005 store factory | — |
| 5 | TASK-MEM-006 app shell | — |
| 6 | TASK-MEM-009 unit suite ∥ TASK-MEM-010 integration semantics | ⚡ 2-way (`tests/unit/` vs `tests/integration/`) |
| 7 | TASK-MEM-011 boundaries ∥ TASK-MEM-012 metadata+concurrency | ⚡ 2-way (disjoint test files) |
| 8 | TASK-MEM-013 assumption record · TASK-MEM-008 NAS deploy (operator, skipped by AutoBuild) | mixed |

Execution preference (Context B): **auto-detect** — /feature-build runs the 2-way waves concurrently where the environment allows, sequential otherwise. Estimated ~10.5 h AutoBuild total, ~6.5–7 h critical path. Integration waves (6–7) need Docker + Tailscale route to GB10; unit gates need neither.

## Assumption Verification Map (Context A: defaults + verify)

| Assumption | Placeholder | Encoded as | Measured by | Recorded by |
|---|---|---|---|---|
| ASSUM-004 pool overflow queues | pool=10 | `pg_pool_max=10` | TASK-MEM-010 (15 concurrent aputs) | TASK-MEM-013 |
| ASSUM-006 startup fail-fast | ≤10 s | `pg_connect_timeout_s=10.0` | TASK-MEM-006 + 010 (closed port) | TASK-MEM-013 |
| ASSUM-008 embed bound | 10 s | `embed_timeout_s=10.0` | TASK-MEM-003 (MockTransport hang) | TASK-MEM-013 |
| ASSUM-002 default search limit | ≤10 | store default | TASK-MEM-011 | TASK-MEM-013 |

## Risks (from review — full detail in the report)

- **R1** psycopg-pool may raise on overflow rather than queue → TASK-MEM-010 AC6 detects; record-and-revise, not blocking
- **R2** integration tier needs Tailscale to GB10 → marker exclusion keeps the default run hermetic; documented in pytest config
- **R3** initdb scripts don't re-run on existing volumes → fixture uses `down -v` + fresh anonymous volumes; pgvector presence asserted after startup
- **R4** health-check race before init SQL completes → fixture waits on `pg_isready` healthcheck, not the port
- **R5** `langgraph-checkpoint-postgres` index-config shape unverified → TASK-MEM-001 import AC + TASK-MEM-005 verification AC surface it in Wave 1/4
- **R6** stray operator `.env` could hijack the test tier → env-var-over-dotenv precedence asserted in TASK-MEM-002

## Operator Follow-up

One task is `operator_handoff`: **TASK-MEM-008** (NAS deploy execution + smoke
G2–G5 + reboot persistence G6). AutoBuild skips it; `/feature-complete` surfaces
its checklist after merge. Prerequisite one-time Phase 0 (SSH key, sudoers,
firewall) is in the runbook.
Write README.md
64 lines
# Feature: Memory Storage Substrate (FEAT-CA81 / FEAT-MEM-01)

The storage substrate for fleet-memory: LangGraph `AsyncPostgresStore` on
Postgres 16 + pgvector with a 768-dimension nomic-embed-text-v1.5 embed function
served by llama-swap on GB10 (:9000).

## Problem

Phase CORE replaces Graphiti as the fleet's development-knowledge memory.
Everything downstream (typed registry, deterministic writer, relay consumer,
retrieval, MCP server — FEAT-MEM-02..09) sits on this substrate. The repo starts
from zero Python; this feature lands the package, the store, the configuration,
the dual deployment topology, and the three-tier test strategy.

## Solution approach

- **Hermetic first** (the chosen trade-off): `deploy/local/` ephemeral compose —
  UUID-named project, random port, throwaway volume — backs ALL automated gates.
  The full suite passes with the NAS powered off; AutoBuild never touches the NAS.
- **Durable second**: `deploy/nas/` compose + `deploy.sh` + `smoke.sh` productized
  from the runbook (gates G2–G5); executed by the operator, not by AutoBuild
  (TASK-MEM-008 is `operator_handoff`).
- **Store core**: settings (`FLEET_MEMORY_` prefix) → httpx embed callable
  (768-dim guard, bounded timeout) → `async_store_context` factory →
  FastStream app shell with lifespan wiring (no subscribers until FEAT-MEM-04).
- **Three test tiers**: fake-embed unit tests (no network, no DB), marker-gated
  integration tests (ephemeral Postgres + real nomic over Tailscale), one
  documented NAS smoke (operator).

## Subtasks

| ID | Title | Type | Cx | Wave |
|---|---|---|---|---|
| TASK-MEM-001 | Scaffold project layout | scaffolding | 3 | 1 |
| TASK-MEM-002 | Settings class and env profiles | declarative | 3 | 2 |
| TASK-MEM-003 | Embed callable with dimension guard | feature | 4 | 3 |
| TASK-MEM-004 | Local ephemeral compose and fixtures | infrastructure | 5 | 2 |
| TASK-MEM-005 | Store factory and namespace validation | feature | 5 | 4 |
| TASK-MEM-006 | App shell with lifespan-managed store | feature | 4 | 5 |
| TASK-MEM-007 | NAS deploy files | infrastructure | 4 | 3 |
| TASK-MEM-008 | NAS deploy execution (operator) | operator_handoff | 1 | 8 |
| TASK-MEM-009 | Unit test suite completion | testing | 4 | 6 |
| TASK-MEM-010 | Integration: store semantics + pool | testing | 6 | 6 |
| TASK-MEM-011 | Integration: boundaries + embed failures | testing | 5 | 7 |
| TASK-MEM-012 | Integration: metadata + concurrency | testing | 5 | 7 |
| TASK-MEM-013 | Assumption verification record | documentation | 1 | 8 |

## Key references

- [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md) — diagrams, contracts, waves
- [Review report](../../../.claude/reviews/TASK-REV-CA81-review-report.md) — options analysis
- `features/storage-substrate/storage-substrate.feature` — 34 BDD scenarios (tagged `@task:` by feature-plan Step 11)
- `docs/runbooks/RUNBOOK-nas-postgres-deploy.md` — NAS deploy source of truth
- `docs/research/ideas/phase-core-build-plan.md` §FEAT-MEM-01

## Acceptance criteria (build plan)

- [ ] `store.aput` / `asearch` round-trip with real nomic embeddings against the ephemeral instance
- [ ] Full test suite passes on the MacBook with the NAS powered off
- [ ] NAS deployed via `deploy.sh`; `smoke.sh` (G2–G5) passes from the Mac
- [ ] Vector index at 768 dims; similarity search with metadata filter
- [ ] No hyphens in any Postgres identifier; underscores in namespace tuples
- [ ] Pool opens/closes cleanly under lifespan; settings via env only
Feature structure complete. Now generating the structured YAML (Step 10) — this also transitively runs the AC-quality linter and the R2/R3 nudges:

Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
Bash Generate structured feature YAML with task graph
IN
python3 ~/.agentecflow/bin/generate-feature-yaml \
    --name "Memory Storage Substrate" \
    --description "LangGraph AsyncPostgresStore on Postgres 16 + pgvector with 768-dim nomic embed function via llama-swap; dual deploy targets (ephemeral local for hermetic gates, durable NAS); lifespan-managed pool; pydantic-settings profiles; three-tier test strategy. FEAT-MEM-01 of Phase CORE." \
    --feature-id FEAT-CA81 \
    --feature-slug "storage-substrate" \
    --discover \
    --task "TASK-MEM-001:Scaffold project layout:3:" \
    --task "TASK-MEM-002:Settings class and env profiles:3:TASK-MEM-001" \
    --task "TASK-MEM-003:Embed callable with dimension guard:4:TASK-MEM-002" \
    --task "TASK-MEM-004:Local ephemeral compose and pytest fixtures:5:TASK-MEM-001" \
    --task "TASK-MEM-005:Store factory and namespace validation:5:TASK-MEM-002,TASK-MEM-003" \
    --task "TASK-MEM-006:App shell with lifespan-managed store:4:TASK-MEM-003,TASK-MEM-005" \
    --task "TASK-MEM-007:NAS deploy files:4:TASK-MEM-004" \
    --task "TASK-MEM-008:NAS deploy execution and smoke by operator:1:TASK-MEM-007" \
    --task "TASK-MEM-009:Unit test suite completion:4:TASK-MEM-003,TASK-MEM-005,TASK-MEM-006" \
    --task "TASK-MEM-010:Integration tests for store semantics and pool lifecycle:6:TASK-MEM-004,TASK-MEM-005,TASK-MEM-006" \
    --task "TASK-MEM-011:Integration tests for search boundaries and embed failures:5:TASK-MEM-010" \
    --task "TASK-MEM-012:Integration tests for metadata filters and concurrency:5:TASK-MEM-010" \
    --task "TASK-MEM-013:Assumption verification record:1:TASK-MEM-009,TASK-MEM-010,TASK-MEM-011,TASK-MEM-012" \
    --base-path "." 2>&1

OUT
/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages/langchain_core/_api/deprecation.py:25: UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.
  from pydantic.v1.fields import FieldInfo as FieldInfoV1
   [discover] TASK-MEM-002: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-002-settings-class-and-env-profiles.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-002-settings-class-env-profiles.md
   [discover] TASK-MEM-003: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-003-embed-callable-with-dimension-guard.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-003-embed-callable-dimension-guard.md
   [discover] TASK-MEM-004: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-004-local-ephemeral-compose-and-pytest-fixtures.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-004-local-ephemeral-compose-fixtures.md
   [discover] TASK-MEM-005: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-005-store-factory-and-namespace-validation.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-005-store-factory-namespace-validation.md
   [discover] TASK-MEM-006: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-006-app-shell-with-lifespan-managed-store.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-006-app-shell-lifespan.md
   [discover] TASK-MEM-008: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-008-nas-deploy-execution-and-smoke-by-operator.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-008-nas-deploy-operator-execution.md
   [discover] TASK-MEM-009: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-009-unit-test-suite-completion.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-009-unit-test-suite.md
   [discover] TASK-MEM-010: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-010-integration-tests-for-store-semantics-and-pool-lif.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-010-integration-store-semantics.md
   [discover] TASK-MEM-011: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-011-integration-tests-for-search-boundaries-and-embed.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-011-integration-boundaries-embed-failures.md
   [discover] TASK-MEM-012: derived path differs from disk, using disk path
     derived: tasks/backlog/storage-substrate/TASK-MEM-012-integration-tests-for-metadata-filters-and-concurr.md
     actual:  tasks/backlog/storage-substrate/TASK-MEM-012-integration-metadata-concurrency.md
✅ Feature FEAT-CA81 created
📋 Tasks: 13
   TASK-MEM-001: Scaffold project layout (complexity: 3)
   TASK-MEM-002: Settings class and env profiles (complexity: 3) (deps: TASK-MEM-001)
   TASK-MEM-003: Embed callable with dimension guard (complexity: 4) (deps: TASK-MEM-002)
   TASK-MEM-004: Local ephemeral compose and pytest fixtures (complexity: 5) (deps: TASK-MEM-001)
   TASK-MEM-005: Store factory and namespace validation (complexity: 5) (deps: TASK-MEM-002, TASK-MEM-003)
   TASK-MEM-006: App shell with lifespan-managed store (complexity: 4) (deps: TASK-MEM-003, TASK-MEM-005)
   TASK-MEM-007: NAS deploy files (complexity: 4) (deps: TASK-MEM-004)
   TASK-MEM-008: NAS deploy execution and smoke by operator (complexity: 1) (deps: TASK-MEM-007)
   TASK-MEM-009: Unit test suite completion (complexity: 4) (deps: TASK-MEM-003, TASK-MEM-005, TASK-MEM-006)
   TASK-MEM-010: Integration tests for store semantics and pool lifecycle (complexity: 6) (deps: TASK-MEM-004, TASK-MEM-005, TASK-MEM-006)
   TASK-MEM-011: Integration tests for search boundaries and embed failures (complexity: 5) (deps: TASK-MEM-010)
   TASK-MEM-012: Integration tests for metadata filters and concurrency (complexity: 5) (deps: TASK-MEM-010)
   TASK-MEM-013: Assumption verification record (complexity: 1) (deps: TASK-MEM-009, TASK-MEM-010, TASK-MEM-011, TASK-MEM-012)

🔀 Parallel execution groups: 8 waves
   Wave 1: [TASK-MEM-001]
   Wave 2: [TASK-MEM-002, TASK-MEM-004]
   Wave 3: [TASK-MEM-003, TASK-MEM-007]
   Wave 4: [TASK-MEM-005, TASK-MEM-008]
   Wave 5: [TASK-MEM-006]
   Wave 6: [TASK-MEM-009, TASK-MEM-010]
   Wave 7: [TASK-MEM-011, TASK-MEM-012]
   Wave 8: [TASK-MEM-013]

📁 Feature file: .guardkit/features/FEAT-CA81.yaml
⚡ AutoBuild ready: /feature-build FEAT-CA81

AC-quality review: 0 unverifiable acceptance criteria detected.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  Feature-level smoke gates (R3) not configured
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This feature has 8 waves but no smoke_gates: key in the generated YAML.
Between-wave smoke checks will not fire during autobuild.

This is the gate that catches composition failures (e.g., the PEX-014..020
"13/13 green + e2e broken" pattern) that per-task Coach approval misses.

Note: no `tests/` directory discovered in this repo — replace the path below
with the directory that holds your test suite.

To activate: add a smoke_gates: block to the feature YAML before running
/feature-build. Minimal example:
    # smoke_gates is ONE object per feature (not a dict-of-waves).
    # after_wave selects which wave(s) the single command fires after.
    smoke_gates:
      after_wave: [2, 3]          # int | list[int] | "all"
      command: |                  # single shell command (multi-line OK)
        set -e
        pytest tests/smoke -x
      expected_exit: 0            # optional, default 0
      timeout: 120                # optional, default 120s, bounds [1, 600]

See installer/core/commands/feature-plan.md § "Smoke gates".
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Read FEAT-CA81.yaml
Edit TASK-MEM-008-nas-deploy-operator-execution.md
Modified
Edit FEAT-CA81.yaml
Added 11 lines
Edit README.md
Modified
Edit IMPLEMENTATION-GUIDE.md
Modified
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
Bash Run feature validation and smoke-gates path validation
IN
~/.agentecflow/bin/guardkit feature validate FEAT-CA81 2>&1 | grep -v "UserWarning\|pydantic.v1"; echo "===EXIT: $?==="; echo "===SMOKE GATES VALIDATION==="; python3 ~/.agentecflow/bin/generate-feature-yaml --validate-smoke-gates --feature-id FEAT-CA81 --base-path . 2>&1 | grep -v "UserWarning\|pydantic.v1"; echo "===EXIT: $?==="

OUT
INFO:guardkit.orchestrator.feature_loader:Loading feature from /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/features/FEAT-CA81.yaml
✗ Feature FEAT-CA81 has validation errors:

Structural errors:
smoke_gates.command references non-existent path:
  tests/unit   (repo root: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory)
Available test roots: (none — no tests/<name> subdirectories found)
===EXIT: 0===
===SMOKE GATES VALIDATION===
smoke_gates.command references non-existent path:
  tests/unit   (repo root: .)
Available test roots: (none — no tests/<name> subdirectories found)
===EXIT: 0===
Bash Create test root placeholders and re-run validators
IN
mkdir -p tests/unit tests/integration && touch tests/unit/.gitkeep tests/integration/.gitkeep && ~/.agentecflow/bin/guardkit feature validate FEAT-CA81 2>&1 | grep -v "UserWarning\|pydantic.v1"; echo "===SMOKE==="; python3 ~/.agentecflow/bin/generate-feature-yaml --validate-smoke-gates --feature-id FEAT-CA81 --base-path . 2>&1 | grep -v "UserWarning\|pydantic.v1"; echo "EXIT=$?"

OUT
INFO:guardkit.orchestrator.feature_loader:Loading feature from /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/features/FEAT-CA81.yaml
✓ Feature FEAT-CA81 is valid
===SMOKE===
✓ smoke_gates.command paths OK
EXIT=0
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
Bash Prepare BDD scenario-to-task matching request
IN
REQ_FILE=$(mktemp -t bdd-link-req-XXXXXX.json) && RESP_FILE=$(mktemp -t bdd-link-resp-XXXXXX.json) && echo "REQ_FILE=$REQ_FILE" && echo "RESP_FILE=$RESP_FILE" && python3 ~/.agentecflow/bin/feature-plan-bdd-link prepare \
    --project-root . \
    --feature-slug "storage-substrate" \
    --feature-yaml ".guardkit/features/FEAT-CA81.yaml" \
    --output "$REQ_FILE" 2>&1 | grep -v "UserWarning\|pydantic.v1"

OUT
REQ_FILE=/var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-req-XXXXXX.json.KUqyIi2B1w
RESP_FILE=/var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-resp-XXXXXX.json.t3DZbLvgrU
{"status": "ready", "feature_path": "/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate.feature", "scenarios_to_match": 34, "task_count": 13, "confidence_threshold": 0.6, "already_tagged_count": 0, "request_path": "/var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-req-XXXXXX.json.KUqyIi2B1w"}
Prepare returned ready: 34 scenarios × 13 tasks. Reading the request payload and invoking the bdd-linker agent:

Bash Read BDD matching request payload
IN
cat /var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-req-XXXXXX.json.KUqyIi2B1w

OUT
<persisted-output>
Output too large (34.6KB). Full output saved to: /Users/richardwoollcott/.claude/projects/-Users-richardwoollcott-Projects-appmilla-github-fleet-memory/1e9796e2-b0b2-428e-9269-04718afdff32/tool-results/br82mi86q.txt

Preview (first 2KB):
{
  "feature_path": "/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate.feature",
  "feature_name": "Memory Storage Substrate",
  "confidence_threshold": 0.6,
  "scenarios": [
    {
      "index": 0,
      "keyword": "Scenario",
      "name": "Storing a memory and retrieving it by its key",
      "description": "",
      "steps": [
        "Giventhe memory store is connected and ready",
        "WhenI store a memory with searchable content under a namespace and key",
        "Thenretrieving that namespace and key should return the same content",
        "Andthe memory should record when it was created and last updated"
      ],
      "existing_tags": [
        "@key-example",
        "@smoke"
      ]
    },
    {
      "index": 1,
      "keyword": "Scenario",
      "name": "Storing to an existing key replaces the previous memory",
      "description": "",
      "steps": [
        "Givena memory already exists under a namespace and key",
        "WhenI store new content under the same namespace and key",
        "Thenretrieving that key should return only the new content",
        "Andno duplicate entry should exist for that key"
      ],
      "existing_tags": [
        "@key-example"
      ]
    },
    {
      "index": 2,
      "keyword": "Scenario",
      "name": "Deleting a memory removes it from retrieval and search",
      "description": "",
      "steps": [
        "Givena stored memory that appears in semantic search results",
        "WhenI delete that memory",
        "Thenretrieving its key should return nothing",
        "Andit should no longer appear in any search results"
      ],
      "existing_tags": [
        "@key-example"
      ]
    },
    {
      "index": 3,
      "keyword": "Scenario",
      "name": "Semantic search returns memories ranked by relevance to the query",
      "description": "",
      "steps": [
...
</persisted-output>
The payload is 34.6KB — the bdd-linker agent has Read access, so I'll point it at the request file directly:

Agent:Match scenarios to tasks storage-substrate
IN
Read the BDD scenario-to-task matching request at:

/var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-req-XXXXXX.json.KUqyIi2B1w

It contains the full matching request JSON for feature "Memory Storage Substrate" (feature file features/storage-substrate/storage-substrate.feature): 34 scenarios (with index, name, steps, existing_tags) and 13 candidate tasks (TASK-MEM-001 .. TASK-MEM-013) with their names/descriptions, confidence_threshold 0.6.

Match every scenario to the task that IMPLEMENTS/VERIFIES it, per your output contract. Guidance on this feature's task split:
- Store semantics scenarios (round-trip, upsert-replace, delete, ranked search, pool lifecycle, pool pressure) → the integration test task for store semantics and pool lifecycle
- Search limit boundaries, default limit, empty store, embed-service-down atomicity, hostile content → the integration test task for search boundaries and embed failures
- Metadata filter, concurrent writes, read-during-write → the integration test task for metadata filters and concurrency
- Ephemeral instance lifecycle, parallel isolation, aborted-run cleanup, integration-run-without-docker → the local ephemeral compose and fixtures task
- Settings/profile selection, missing settings → the settings task
- Dimension boundary/mismatch rows, hung embedding service → the embed callable task
- Service refuses to start on unreachable DB, pool lives/dies with service → the app shell lifespan task
- Unit-tests-without-infrastructure, credential hygiene → the unit test suite task
- NAS smoke check, NAS restart survival, NAS refuses outside connections → the NAS operator execution task
- Namespace hyphen rejection → the store factory task
- Full-suite-with-NAS-off → the integration metadata/concurrency task (suite-level green) or the fixtures task — pick the better fit
- 768-dim exact storage → embed callable or store semantics — pick the better fit

Return ONLY the JSON array of TaskMatch objects (scenario_index, scenario_name, task_id, confidence, rationale) — no prose, no markdown fences, exactly per your Output Contract.
Read bdd-link-req-XXXXXX.json.KUqyIi2B1w
All 34 scenarios matched above threshold. Writing the response verbatim and applying:

Bash Apply BDD scenario-to-task matches to feature file
IN
cat > /var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-resp-XXXXXX.json.t3DZbLvgrU <<'EOF'
[{"scenario_index":0,"task_id":"TASK-MEM-010","confidence":0.92},{"scenario_index":1,"task_id":"TASK-MEM-010","confidence":0.91},{"scenario_index":2,"task_id":"TASK-MEM-010","confidence":0.91},{"scenario_index":3,"task_id":"TASK-MEM-010","confidence":0.93},{"scenario_index":4,"task_id":"TASK-MEM-012","confidence":0.92},{"scenario_index":5,"task_id":"TASK-MEM-006","confidence":0.91},{"scenario_index":6,"task_id":"TASK-MEM-002","confidence":0.92},{"scenario_index":7,"task_id":"TASK-MEM-004","confidence":0.93},{"scenario_index":8,"task_id":"TASK-MEM-008","confidence":0.88},{"scenario_index":9,"task_id":"TASK-MEM-008","confidence":0.90},{"scenario_index":10,"task_id":"TASK-MEM-004","confidence":0.82},{"scenario_index":11,"task_id":"TASK-MEM-009","confidence":0.93},{"scenario_index":12,"task_id":"TASK-MEM-010","confidence":0.78},{"scenario_index":13,"task_id":"TASK-MEM-003","confidence":0.93},{"scenario_index":14,"task_id":"TASK-MEM-011","confidence":0.93},{"scenario_index":15,"task_id":"TASK-MEM-011","confidence":0.93},{"scenario_index":16,"task_id":"TASK-MEM-011","confidence":0.92},{"scenario_index":17,"task_id":"TASK-MEM-006","confidence":0.91},{"scenario_index":18,"task_id":"TASK-MEM-002","confidence":0.92},{"scenario_index":19,"task_id":"TASK-MEM-011","confidence":0.91},{"scenario_index":20,"task_id":"TASK-MEM-008","confidence":0.88},{"scenario_index":21,"task_id":"TASK-MEM-005","confidence":0.93},{"scenario_index":22,"task_id":"TASK-MEM-004","confidence":0.91},{"scenario_index":23,"task_id":"TASK-MEM-012","confidence":0.93},{"scenario_index":24,"task_id":"TASK-MEM-010","confidence":0.88},{"scenario_index":25,"task_id":"TASK-MEM-004","confidence":0.92},{"scenario_index":26,"task_id":"TASK-MEM-004","confidence":0.91},{"scenario_index":27,"task_id":"TASK-MEM-006","confidence":0.78},{"scenario_index":28,"task_id":"TASK-MEM-008","confidence":0.82},{"scenario_index":29,"task_id":"TASK-MEM-009","confidence":0.91},{"scenario_index":30,"task_id":"TASK-MEM-011","confidence":0.88},{"scenario_index":31,"task_id":"TASK-MEM-012","confidence":0.91},{"scenario_index":32,"task_id":"TASK-MEM-003","confidence":0.88},{"scenario_index":33,"task_id":"TASK-MEM-008","confidence":0.75}]
EOF
python3 ~/.agentecflow/bin/feature-plan-bdd-link apply \
    --project-root . \
    --feature-slug "storage-substrate" \
    --task-matches-file /var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-resp-XXXXXX.json.t3DZbLvgrU 2>&1 | grep -v "UserWarning\|pydantic.v1"; echo "EXIT=$?"

OUT
[Step 11] linked 34 scenario(s) to task(s); 0 already tagged; 0 below threshold (0.60) (of 34 total)
EXIT=0
All 34 scenarios linked. Spot-checking the tags, cleaning up temp files, then completing the workflow bookkeeping:

Bash Verify @task tags applied and clean up temp files
IN
grep -c "@task:" features/storage-substrate/storage-substrate.feature; grep -B1 "Scenario: Storing a memory and retrieving" features/storage-substrate/storage-substrate.feature | head -3; rm -f /var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-req-XXXXXX.json.KUqyIi2B1w /var/folders/75/prgjl4_x0k3_6tj58k39db1r0000gn/T/bdd-link-resp-XXXXXX.json.t3DZbLvgrU /tmp/review-analysis.md

OUT
34
  @key-example @smoke
  Scenario: Storing a memory and retrieving it by its key
34 @task: tags present — checking placement format:

Bash Inspect tag placement in feature file
IN
sed -n '20,28p' features/storage-substrate/storage-substrate.feature; echo "..."; grep -n "@task:TASK-MEM-008" features/storage-substrate/storage-substrate.feature | head -5

OUT
  # Why: Core round-trip — defines what "storing a memory" means
  @task:TASK-MEM-010
  @key-example @smoke
  Scenario: Storing a memory and retrieving it by its key
    Given the memory store is connected and ready
    When I store a memory with searchable content under a namespace and key
    Then retrieving that namespace and key should return the same content
    And the memory should record when it was created and last updated
...
107:  @task:TASK-MEM-008
116:  @task:TASK-MEM-008
234:  @task:TASK-MEM-008
309:  @task:TASK-MEM-008
356:  @task:TASK-MEM-008
Edit phase-core-build-plan.md
Modified
Edit phase-core-build-plan.md
Modified
Edit TASK-REV-CA81-plan-memory-storage-substrate.md
Edit failed
Read TASK-REV-CA81-plan-memory-storage-substrate.md
Edit TASK-REV-CA81-plan-memory-storage-substrate.md
Added 2 lines
Bash Archive completed review task and list final structure
IN
mkdir -p tasks/completed/2026-06 && mv tasks/in_review/TASK-REV-CA81-plan-memory-storage-substrate.md tasks/completed/2026-06/ && ls tasks/completed/2026-06/ tasks/backlog/storage-substrate/

OUT
tasks/backlog/storage-substrate/:
IMPLEMENTATION-GUIDE.md
README.md
TASK-MEM-001-scaffold-project-layout.md
TASK-MEM-002-settings-class-env-profiles.md
TASK-MEM-003-embed-callable-dimension-guard.md
TASK-MEM-004-local-ephemeral-compose-fixtures.md
TASK-MEM-005-store-factory-namespace-validation.md
TASK-MEM-006-app-shell-lifespan.md
TASK-MEM-007-nas-deploy-files.md
TASK-MEM-008-nas-deploy-operator-execution.md
TASK-MEM-009-unit-test-suite.md
TASK-MEM-010-integration-store-semantics.md
TASK-MEM-011-integration-boundaries-embed-failures.md
TASK-MEM-012-integration-metadata-concurrency.md
TASK-MEM-013-assumption-verification-record.md

tasks/completed/2026-06/:
TASK-REV-CA81-plan-memory-storage-substrate.md
Update Todos

Context A: review scope clarification (agent + user)

Create review task via /task-create

Execute /task-review --mode=decision

Present decision checkpoint [A/R/I/C]

Context B: implementation preferences (if Implement)

Create feature folder + subtasks + IMPLEMENTATION-GUIDE with Mermaid diagrams

Generate feature YAML (generate-feature-yaml --discover)

Pre-flight validation (guardkit feature validate + smoke gates)

Step 11: BDD scenario linking (@task tags)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE PLANNING COMPLETE — FEAT-CA81: Memory Storage Substrate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FEAT-MEM-01 is fully planned: 13 tasks across 8 waves, AutoBuild-ready, with all 34 BDD scenarios wired to tasks. Your clarification decisions (hermetic correctness as the trade-off priority; assumptions as verify-and-record defaults; recommended bundle confirmed) are baked into the task acceptance criteria.

Created:

📁 Feature file: .guardkit/features/FEAT-CA81.yaml — validated ✓ (task paths, waves, dependencies, task types, smoke-gate paths all green)
📋 Task tree: tasks/backlog/storage-substrate/ — 13 tasks + README + IMPLEMENTATION-GUIDE (data-flow, sequence, and dependency diagrams; §4 Integration Contracts incl. the psycopg3-not-asyncpg DSN format; seam test stubs in consumer tasks)
🔍 Review report: .claude/reviews/TASK-REV-CA81-review-report.md (review task archived to completed)
🔗 BDD: all 34 scenarios tagged @task: (R2 oracle active); smoke gate pytest tests/unit fires after every wave (R3 active — tests/unit|integration/ roots pre-declared so path validation passes)
📝 Build plan flipped to Plan'd with the FEAT-CA81 id
Operator follow-up tasks: 1 — TASK-MEM-008 (NAS deploy + smoke G2–G5 + reboot G6) is operator_handoff; AutoBuild skips it and /feature-complete will surface its checklist post-merge.

Execution plan (auto-detect parallelism, ~10.5h total / ~6.5–7h critical path):

Wave	Tasks
1	MEM-001 scaffold
2	MEM-002 settings ∥ MEM-004 ephemeral compose+fixtures
3	MEM-003 embed ∥ MEM-007 NAS files
4	MEM-005 store factory (+ MEM-008 operator slot)
5	MEM-006 app shell
6	MEM-009 unit suite ∥ MEM-010 integration semantics
7	MEM-011 boundaries ∥ MEM-012 metadata+concurrency
8	MEM-013 assumption record
One judgement call to know about: the data-flow diagram carries a deliberate disconnection alert — the NAS durable instance has no production read/write path inside this feature (only the operator smoke gate). That's by design; production paths arrive with FEAT-MEM-03/04/05, and the deferral is documented in the guide per the disconnection rule.

Next steps:

Review IMPLEMENTATION-GUIDE.md — the data-flow diagram and §4 contracts are the primary review artefacts
Commit the plan (spec + plan commits are pending per the build plan convention)
Start the build: /feature-build FEAT-CA81
After Wave 3 lands, the NAS deploy (TASK-MEM-008) can run any time — it only needs the deploy/nas/ files
Note: integration waves (6–7) need Docker running and the Tailscale route to GB10; unit gates and the smoke gate need neither — the default suite stays hermetic with the NAS powered off, exactly as the spec demands.