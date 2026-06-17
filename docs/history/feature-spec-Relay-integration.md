/feature-spec "Relay integration: FastStream durable consumer on MEMORY stream consuming MemoryEpisodeV1 from nats-core; structured_json episodes dispatch through payload registry to deterministic writer; markdown/text episodes chunk+embed with heading-aware chunking; ack/nak/DLQ per relay scope; TestNatsBroker test suite incl. poison message and redelivery idempotency"



I'll execute the /feature-spec command through its six phases. Let me start with Phase 1: Context Gathering (silent).

Bash Detect stack and existing feature files
IN
ls -la && echo "---PYPROJECT---" && ls pyproject.toml setup.py requirements.txt 2>/dev/null && echo "---FEATURES---" && find features -name "*.feature" 2>/dev/null | head -20

OUT
Exit code 1
total 376
drwxr-xr-x   33 richardwoollcott  staff   1056 Jun 13 08:22 .
drwxr-xr-x  173 richardwoollcott  staff   5536 Jun 12 12:43 ..
drwxr-xr-x@  11 richardwoollcott  staff    352 Jun 12 16:41 .claude
-rw-r--r--    1 richardwoollcott  staff   1771 Jun 13 08:22 .env.example
drwxr-xr-x   17 richardwoollcott  staff    544 Jun 13 11:58 .git
-rw-r--r--@   1 richardwoollcott  staff   4723 Jun 12 13:02 .gitignore
drwxr-xr-x@  10 richardwoollcott  staff    320 Jun 13 08:22 .guardkit
-rw-r--r--    1 richardwoollcott  staff      0 Jun 13 08:22 .guardkit-git.lock
drwxr-xr-x@   6 richardwoollcott  staff    192 Jun 12 22:51 .pytest_cache
drwxr-xr-x@   7 richardwoollcott  staff    224 Jun 13 08:22 .venv
-rw-r--r--    1 richardwoollcott  staff  15711 Jun 13 08:22 coverage_all.json
-rw-r--r--    1 richardwoollcott  staff   3318 Jun 13 08:22 coverage_final.json
-rw-r--r--    1 richardwoollcott  staff  15663 Jun 13 08:22 coverage_integration.json
-rw-r--r--    1 richardwoollcott  staff  15663 Jun 13 08:22 coverage_phase4_new.json
-rw-r--r--    1 richardwoollcott  staff  15302 Jun 13 08:22 coverage_phase4_test.json
-rw-r--r--    1 richardwoollcott  staff  22820 Jun 13 08:22 coverage_phase4.json
-rw-r--r--    1 richardwoollcott  staff  14788 Jun 13 08:22 coverage_review.json
-rw-r--r--    1 richardwoollcott  staff   3318 Jun 13 08:22 coverage_test.json
-rw-r--r--    1 richardwoollcott  staff  15290 Jun 13 08:22 coverage.json
drwxr-xr-x    4 richardwoollcott  staff    128 Jun 13 08:22 deploy
drwxr-xr-x@   4 richardwoollcott  staff    128 Jun 12 15:28 docs
drwxr-xr-x    5 richardwoollcott  staff    160 Jun 13 11:20 features
-rw-r--r--    1 richardwoollcott  staff   1065 Jun 12 12:43 LICENSE
drwxr-xr-x@   2 richardwoollcott  staff     64 Jun 12 15:18 migrations
-rw-r--r--    1 richardwoollcott  staff   1191 Jun 13 08:22 pyproject.toml
-rw-r--r--    1 richardwoollcott  staff     38 Jun 12 12:43 README.md
drwxr-xr-x    4 richardwoollcott  staff    128 Jun 13 08:22 src
drwxr-xr-x@   8 richardwoollcott  staff    256 Jun 13 08:22 tasks
-rw-r--r--    1 richardwoollcott  staff  10326 Jun 13 08:22 test_all_output.txt
-rw-r--r--    1 richardwoollcott  staff   3192 Jun 13 08:22 test_integration_output.txt
-rw-r--r--    1 richardwoollcott  staff  10645 Jun 13 08:22 test_output.txt
-rw-r--r--    1 richardwoollcott  staff   5646 Jun 13 08:22 test_phase4_output.txt
drwxr-xr-x    8 richardwoollcott  staff    256 Jun 13 08:22 tests
---PYPROJECT---
pyproject.toml
Bash List Python source files
IN
echo "---SRC TREE---" && find src app lib -type f -name "*.py" 2>/dev/null | head -60

OUT
---SRC TREE---
src/fleet_memory/store.py
src/fleet_memory/embed.py
src/fleet_memory/__init__.py
src/fleet_memory/settings.py
src/fleet_memory/app.py
src/fleet_memory/errors.py
Bash List features, tests, pyproject
IN
echo "===FEATURES===" && find features -type f 2>/dev/null && echo "===TESTS===" && find tests -type f -name "*.py" 2>/dev/null && echo "===MIGRATIONS===" && ls migrations/ && echo "===PYPROJECT===" && cat pyproject.toml

OUT
===FEATURES===
features/storage-substrate/storage-substrate_summary.md
features/storage-substrate/storage-substrate.feature
features/storage-substrate/storage-substrate_assumptions.yaml
features/deterministic-writer/deterministic-writer_summary.md
features/deterministic-writer/deterministic-writer_assumptions.yaml
features/deterministic-writer/deterministic-writer.feature
features/typed-payload-registry/typed-payload-registry_assumptions.yaml
features/typed-payload-registry/typed-payload-registry_summary.md
features/typed-payload-registry/typed-payload-registry.feature
===TESTS===
tests/conftest.py
tests/__init__.py
tests/test_assumptions_verification.py
tests/unit/test_fake_embed_fixture.py
tests/unit/test_store_validation.py
tests/unit/__init__.py
tests/unit/test_app_lifespan.py
tests/unit/test_credential_hygiene.py
tests/unit/test_embed.py
tests/unit/test_scaffold.py
tests/unit/test_settings.py
tests/integration/conftest.py
tests/integration/test_ephemeral_fixture.py
tests/integration/__init__.py
tests/integration/test_pool_lifecycle.py
tests/integration/test_store_semantics.py
tests/integration/ollama_wrapper.py
tests/integration/test_concurrent_writes.py
tests/integration/test_injection_safety.py
tests/integration/test_embed_failures.py
tests/integration/test_search_boundaries.py
tests/integration/test_metadata_filter.py
===MIGRATIONS===
===PYPROJECT===
[project]
name = "fleet_memory"
version = "0.1.0"
description = "LangGraph checkpoint and memory store for distributed agent coordination"
requires-python = ">=3.12"
dependencies = [
    "faststream[nats]",
    "pydantic>=2",
    "pydantic-settings>=2",
    "langgraph-checkpoint-postgres>=2.0",
    "httpx",
    "psycopg[binary]",
    "psycopg-pool",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "pytest-timeout",
    "pytest-bdd>=8.1,<9",
    "ruff",
    "pyyaml",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not integration'"
markers = [
    "integration: marks tests as integration tests (deselected by default)",
    "seam: cross-module contract tests",
    "integration_contract: tests that verify integration contracts",
]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
]
Read app.py
Rich existing codebase with related features. Let me read the existing feature specs and source to align conventions and avoid duplication.

Read typed-payload-registry.feature
Read deterministic-writer.feature
High-quality domain-language conventions established. Let me read the build plan, source files, and schemas to ground the relay-integration spec (this is FEAT-MEM-04).

Bash Find docs, schemas, tasks for relay feature
IN
echo "===DOCS RESEARCH===" && find docs -type f | head -40 && echo "===SCHEMAS / PAYLOAD===" && grep -rln "MemoryEpisode\|payload_registry\|PayloadRegistry\|MemoryEpisodeV1" src tests 2>/dev/null && echo "===TASKS===" && ls tasks/ && find tasks -maxdepth 2 -iname "*MEM-04*" -o -iname "*relay*" 2>/dev/null | head

OUT
Exit code 1
===DOCS RESEARCH===
docs/runbooks/RUNBOOK-nas-postgres-deploy.md
docs/research/ideas/phase-core-build-plan.md
docs/research/ideas/phase-core-scope.md
===SCHEMAS / PAYLOAD===
Read settings.py
Let me read the build plan (FEAT-MEM-04 section) and scope doc, plus the store/embed interfaces.

Bash Find relay-relevant lines in build plan
IN
grep -n "FEAT-MEM-04\|FEAT-MEM-05\|relay\|Relay\|MEMORY stream\|MemoryEpisode\|durable\|DLQ\|dead.letter\|poison\|redeliver\|chunk\|heading" docs/research/ideas/phase-core-build-plan.md | head -60

OUT
5:## Predecessor: Memory Relay scope at [`nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md`](../../../../nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md) (capture/buffer layer; D1–D11 inherited except where superseded below)
17:Graphiti is being replaced as the fleet's development-knowledge memory. The full case is in the scope doc; the operational summary: TASK-REV-GROI found 0/10 consumption paths proven high-value; the write path costs ~28GB always-on (`qwen-graphiti`) after every consolidation route failed (findings §9.5–§9.8); the cloud fallback cost £30 in one weekend; and ADR-SP-007 (markdown authoritative) makes replacement a re-index rather than a migration. The Memory Relay (nats-infrastructure) provides durable LLM-free capture; this repo provides the store, the deterministic writer, retrieval, and the MCP surface.
23:| nats-core | `MemoryEpisodeV1` envelope schema + publisher helper | Relay P1 (one small feature) |
24:| nats-infrastructure | MEMORY stream + consumer definitions, provisioning | Relay P2 (definitions only — drain worker does NOT live there; superseded, see RD-3) |
25:| **fleet-memory (this repo)** | Store, typed registry, deterministic writer, relay consumer, retrieval, MCP server, runbooks | FEAT-MEM-01..09 |
30:See scope doc table. Key for sequencing: the template gives Schemas/Handlers/Services layers with TestNatsBroker testing out of the box, so FEAT-MEM-04's consumer is a handler in an existing idiom, not new architecture; and nomic-embed is already always-on, so FEAT-MEM-01 has no serving-layer dependency beyond what's running today.
34:Nine features. 01–03 are the spine (store, schemas, writer); 04–06 are the surfaces (relay, retrieval, MCP); 07–09 are population and cutover. 01→02→03 strictly sequential; 04 and 05 parallelizable after 03; 06 after 05; 07 after 03 (writer exists); 08 after 05+07; 09 last.
43:| FEAT-MEM-04 | Relay integration (MEMORY consumer + chunk/embed path) | Not started | — |
44:| FEAT-MEM-05 | Retrieval API + context assembly | Not started | — |
54:- `MemoryEpisodeV1` frozen v1; engine mapping lives in this repo's services.
65:Postgres 16 + pgvector (durable instance on the Synology NAS per RD-4), `langgraph` `AsyncPostgresStore` with index config `{dims: 768, embed: <nomic via llama-swap :9000>}`, lifespan wiring, pydantic-settings (`FLEET_MEMORY_PG_DSN`, `FLEET_MEMORY_EMBED_URL`, `FLEET_MEMORY_EMBED_MODEL`), store smoke tests (put/get/search round-trip with real embeddings, marker-gated integration tests).
72:| Durable shared Postgres | Synology NAS, Container Manager project (compose + notes in `deploy/nas/`) | Re-index target (07), MCP server, relay consumer, soak | Volume on a backed-up shared folder; port 5432 exposed to LAN/Tailscale only; reachable from the Mac during dev as `FLEET_MEMORY_PG_DSN` pointing at the NAS |
82:# /feature-spec "Storage substrate: LangGraph AsyncPostgresStore on Postgres 16 + pgvector with nomic-embed-text-v1.5 768-dim embed function via llama-swap :9000; dual deploy targets — deploy/local ephemeral compose for hermetic Mac test gates (random-port, throwaway, used by ALL automated tests incl. AutoBuild) and deploy/nas Synology Container Manager compose for the durable shared instance (backed-up volume, LAN/Tailscale-only 5432); lifespan-managed pool; pydantic-settings DSN/embed config with .env.example profiles for mac-dev-vs-nas; fake-embed unit tests + marker-gated integration tests against the ephemeral instance + one documented smoke against the NAS instance"
106:Pydantic models in the Schemas layer: `AdrPayload`, `ReviewReportPayload`, `BuildOutcomePayload`, `PatternPayload`, `WarningPayload`, `SeedModulePayload`, `DocumentPayload` (generic). Conventions: `natural_key` property per type (e.g. `adr:guardkit:ADR_SP_007`), `supersedes: list[str]`, `domain_tags: list[str]`, `source_ref`, version stamp. Registry maps `payload_type` string → model class (the writer and the relay consumer both dispatch through it).
142:## FEAT-MEM-04: Relay Integration
144:FastStream handler on the MEMORY stream durable consumer: `content_format: json` + `payload_type` → registry → writer; `markdown`/`text` → chunking service (heading-aware, ~1K-token chunks, overlap) → embed → store under `("fleet_memory", project, "chunk")` with source_ref metadata. Ack/nak/DLQ semantics per relay scope D5/D9; ingestion ledger via natural keys (relay O3 resolved: the writer's idempotency IS the ledger for structured; chunk path uses episode_id keys). The drain worker concept collapses into this consumer — no residency gating needed, because nothing here needs a big model.
149:/feature-spec "Relay integration: FastStream durable consumer on MEMORY stream consuming MemoryEpisodeV1 from nats-core; structured_json episodes dispatch through payload registry to deterministic writer; markdown/text episodes chunk+embed with heading-aware chunking; ack/nak/DLQ per relay scope; TestNatsBroker test suite incl. poison message and redelivery idempotency"
155:- [ ] Publish 3 structured + 2 markdown episodes via TestNatsBroker → 3 typed records + N chunks
157:- [ ] Malformed body → DLQ subject after max_deliver, consumer continues
160:## FEAT-MEM-05: Retrieval API + Context Assembly
192:- [ ] MCP writes are byte-identical in store form to relay writes of the same payload
197:Two parts. (a) Re-index script: walk guardkit's authoritative markdown (seed modules, ADRs, review reports, completed-task outcomes), parse to typed payloads (deterministic parsers — front-matter and house formats are regular), publish via nats-core helper (exercising the full relay path). (b) Fable backfill: one-time, window-bound job where Fable 5 reads the genuinely unstructured legacy docs and authors typed payloads for human review before publishing — output is reviewed markdown/JSON in the repo, so the result is re-runnable forever without any frontier model.
202:/feature-spec "Re-index pipeline: deterministic markdown-to-typed-payload parsers for guardkit seed modules, ADRs, review reports and task outcomes, publishing via nats-core MemoryEpisodeV1 through the live relay; idempotent full-corpus runs; backfill staging area for Fable-authored payloads with human review gate before publish"
210:- [ ] Stream-vs-store audit script reports 100% accounted (ingested or DLQ'd)
238:| 1 (Fri 12) | This pair; ~~`/feature-spec` + `/feature-plan` FEAT-MEM-01~~ ✅; relay P1 spec in nats-core (on instruction) |
239:| 2–3 (wknd) | ~~FEAT-MEM-01 build~~ ✅ (landed 06-13 @ `2a8ae61`; NAS deploy pending op) + FEAT-MEM-02 build; ~~Postgres live on NAS~~ (pending TASK-MEM-008); relay P2 stream definitions land |
241:| 5 (Tue 16) | FEAT-MEM-04 relay consumer; first end-to-end publish→store |
242:| 6 (Wed 17) | FEAT-MEM-05 retrieval + probe harness; record Graphiti baseline answers before any freeze |
256:| RD-3 | **Supersedes relay D4:** relay consumer (drain worker) lives in fleet-memory | The writer it calls lives here; residency gating dropped — nothing on this write path needs a big model. nats-infrastructure keeps stream/consumer *definitions* only |
260:| RD-7 | No LLM extraction in Phase CORE; unstructured = chunk+embed | Raw episodes persist in MEMORY stream; enrichment stays a future batch option |
267:| OD-1 | Chunking parameters for markdown path (size/overlap/heading awareness) | Start 1K tokens, 15% overlap, heading-aware; tune only on probe-set evidence | FEAT-MEM-04 spec |
268:| OD-2 | Probe-set composition (which 15+ queries, from whose history) | Draw from coach-context + feature-plan invocations in guardkit history files; freeze before FEAT-MEM-05 build | Day 6 |
271:| OD-5 | Runtime host for the relay consumer + MCP-adjacent services in production | GB10 container (compute box: beside NATS and llama-swap, localhost embeddings, LAN to NAS Postgres) — NAS stays storage-only, Mac stays a dev surface that can sleep | FEAT-MEM-04 spec |
278:| Fable window closes before Day 8 backfill | Backfill is staged + reviewable; worst case the unstructured legacy slice ships chunk-only (already the v1 contract) and typed backfill happens later with a local model |
281:| Two write surfaces drift (MCP vs relay) | Both dispatch through the single registry+writer (FEAT-MEM-06 AC enforces byte-identical store form) |
Read phase-core-build-plan.md (lines 143-177)
Bash Find relay semantics in scope doc
IN
echo "===SCOPE D5/D9/episode===" && grep -n "D5\|D9\|episode_id\|content_format\|MemoryEpisode\|max_deliver\|DLQ\|dead.letter\|ack\|nak\|durable\|relay scope\|O3" docs/research/ideas/phase-core-scope.md | head -50

OUT
===SCOPE D5/D9/episode===
5:## Status: **Phase CORE not started.** Repo initialized from `nats-asyncio-service` template 2026-06-12; slash-command capture hook wired same day. Fable 5 subscription window: ~10 days from 2026-06-12 — the one-time backfill (FEAT-MEM-07) and heavy planning sessions must land inside it.
15:> A typed, deterministic memory store (Postgres + pgvector behind LangGraph `AsyncPostgresStore`), fed by the NATS episode relay and embedding with the always-on nomic endpoint, can replace Graphiti as the fleet's development-knowledge memory — with **zero LLM on the write path** for structured content, retrieval quality **≥ Graphiti** on real job-context queries, the **~28GB always-on extraction model retired**, and the **cloud fallback deleted** — built, re-indexed, and cut over inside the 10-day Fable 5 window.
17:If true, `qwen-graphiti` leaves the preload permanently, the Gemini fallback path dies, the guardkit/graphiti fork stops mattering, and every fleet agent (including AWS-deployed ones) gets memory capture as a fire-and-forget NATS publish. If false at the retrieval-quality gate, the diagnosis (filter miss, embedding miss, missing relationship traversal) is recorded against the GROI framework and Graphiti unfreezes — the relay, schemas, and deterministic writer survive that outcome unchanged.
28:| Fable 5 window | ~10 days of frontier capacity for planning sessions and the one-time unstructured-legacy backfill ("teacher funds its own replacement", executed literally) |
38:| Memory Relay scope (capture envelope `MemoryEpisodeV1`, MEMORY stream, drain gating, idempotency, DLQ) | nats-infrastructure spec | ✅ scoped 2026-06-12; relay D1–D11 inherited |
40:| nats-core schema/client package pattern (`pip install git+ssh`) | nats-core | ✅ live; memory schemas are a cross-repo deliverable |
57:| FEAT-MEM-07 | Re-index + Fable backfill — guardkit seeds/ADRs through the writer from markdown; one-time Fable 5 job structuring genuinely unstructured legacy docs into typed payloads | Populates the store from authoritative source (ADR-SP-007 made this free). The backfill is the only frontier-model job in the phase — authored once, inside the window, never needed again. |
59:| FEAT-MEM-09 | Cutover + decommission runbook — preload change, Gemini fallback deletion, Graphiti freeze, stream-vs-store audit | The 28GB reclaim and the clean ending. Runbook in `docs/runbooks/` in house style (phased, PASS/FAIL gates, rollback, what-NOT-to-do). |
67:3. **Zero capture loss.** Stream-vs-store audit over the soak: every `MemoryEpisodeV1` published is either ingested or in DLQ with a recorded reason. No silent losses — the failure mode that started all of this.
68:4. **28GB reclaimed.** `qwen-graphiti` out of the always-on preload; steady-state GB10 memory during interactive hours reduced accordingly; Gemini fallback config deleted (£0 cloud on the memory path).
88:- **DECISION-DF-001.** No cloud API on the dark-factory critical path. Fable 5 is used for *authoring* (planning sessions, one-time backfill content) — never wired into runtime ingestion or retrieval.
90:- **Relay contract frozen.** `MemoryEpisodeV1` is framework-neutral (relay D7) and versioned; fleet-memory adapts to it, never the reverse. Engine-specific mapping lives in this repo's services.
92:- **Underscores everywhere.** `fleet_memory` package, Postgres schema/identifiers, namespace tuples, group identifiers. Hyphens confined to the repo name. (FalkorDB scar tissue; carried as fleet convention.)
Relay D5/D9 semantics live in a sibling repo. Let me check if accessible, and look at store/embed interfaces.

Bash Locate relay scope doc in sibling repo
IN
SCOPE="../../nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md"; if [ -f "$SCOPE" ]; then echo "FOUND"; grep -n "D5\|D9\|max_deliver\|DLQ\|dead.letter\|ack\|nak\|term\|redeliver\|episode_id\|content_format\|MemoryEpisode" "$SCOPE" | head -50; else echo "NOT FOUND at $SCOPE"; find ../.. -iname "*memory-relay*" -maxdepth 5 2>/dev/null | head; find ../.. -iname "*MemoryEpisode*" 2>/dev/null | head; fi

OUT
NOT FOUND at ../../nats-infrastructure/docs/design/specs/memory-relay/memory-relay-scope.md
Bash Inspect store, embed, errors interfaces
IN
echo "===STORE API===" && grep -n "def \|async def \|class \|namespace\|aput\|asearch\|aget\|put\|search" src/fleet_memory/store.py | head -40 && echo "===EMBED API===" && grep -n "def \|async def \|class \|raise\|Error" src/fleet_memory/embed.py | head -30 && echo "===ERRORS===" && grep -n "class \|Error" src/fleet_memory/errors.py | head

OUT
===STORE API===
1:"""Store factory and namespace validation for fleet-memory.
35:def _dsn_target(dsn: str) -> str:
52:def validate_namespace(namespace: tuple[str, ...]) -> None:
53:    """Validate namespace tuple enforces underscores-only identifiers.
56:        namespace: Tuple of namespace identifiers (e.g., ("fleet_memory", "project", "chunk"))
62:        >>> validate_namespace(("fleet_memory", "my_project", "chunk"))  # OK
63:        >>> validate_namespace(("fleet_memory", "my-project", "chunk"))  # Raises
66:    for part in namespace:
71:        raise NamespaceValidationError(namespace=namespace, invalid_parts=invalid_parts)
75:async def async_store_context(
89:        Configured AsyncPostgresStore with index config for semantic search
98:        ...     await store.put(("fleet_memory", "proj", "item"), "key", {"content": "..."})
110:        async def real_embed(texts: list[str]) -> list[list[float]]:
117:    # Configure index for pgvector semantic search
===EMBED API===
15:    EmbedDimensionError,
16:    EmbedServiceError,
17:    EmbedTimeoutError,
24:def _normalize_embed_url(base_url: str) -> str:
41:async def embed(
57:        EmbedDimensionError: If any embedding dimension doesn't match settings.embed_dims
58:        EmbedTimeoutError: If request times out
59:        EmbedServiceError: If service returns error or malformed response
83:            raise EmbedServiceError(
93:            raise EmbedServiceError(
100:            raise EmbedServiceError(
111:                raise EmbedDimensionError(
119:        raise EmbedTimeoutError(
124:        raise EmbedTimeoutError(
128:    except (EmbedDimensionError, EmbedTimeoutError, EmbedServiceError):
129:        # Re-raise our custom exceptions
130:        raise
133:        raise EmbedServiceError(
139:def make_fake_embed(dims: int = 768) -> callable:
151:    async def fake_embed(texts: list[str]) -> list[list[float]]:
===ERRORS===
4:class EmbedDimensionError(ValueError):
7:    Error message includes both actual and expected dimensions.
25:class EmbedTimeoutError(TimeoutError):
43:class EmbedServiceError(RuntimeError):
70:class NamespaceValidationError(ValueError):
Context loaded: stack=python, 6 source modules (store, embed, settings, app, errors, init), 3 existing .feature files (storage-substrate, typed-payload-registry, deterministic-writer — all upstream of this feature), build plan FEAT-MEM-04 + ACs, relay decisions RD-3/RD-7/OD-1. Relay scope D5/D9 lives in the sibling nats-infrastructure repo (not readable here → ack/nak/DLQ specifics become assumptions).

This is FEAT-MEM-04: Relay Integration — the consumer that wires the typed-payload-registry (FEAT-MEM-02) and deterministic-writer (FEAT-MEM-03) onto the MEMORY stream. Here is the full proposal.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC PROPOSAL: Relay Integration (FEAT-MEM-04)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@relay-integration
Feature: Relay Integration
  As the fleet-memory relay consumer on the MEMORY stream
  I want every published MemoryEpisodeV1 routed by its content format — structured payloads through the registry to the deterministic writer, prose chunked and embedded — and acknowledged only once durably stored, with poison episodes parked and redeliveries made inert
  So that capture is fire-and-forget and lossless, no episode is silently dropped, no language model touches the write path, and at-least-once redelivery can never duplicate a memory

  Background:
    Given the relay consumer is subscribed to the MEMORY stream as a durable consumer
    And the typed payload registry and deterministic writer are available
    And the embedding service and store are available

━━ GROUP A: Key Examples (7 scenarios) ━━

  # Why: Core structured path — content_format json dispatches through the registry to the writer
  @key-example @smoke
  Scenario: A structured JSON episode is dispatched through the registry to the deterministic writer
    Given a MemoryEpisodeV1 whose content format is structured JSON for a known payload type
    When the consumer receives the episode
    Then the payload should be dispatched through the registry to the deterministic writer
    And a typed record for that payload should exist in the project namespace
    And the episode should be acknowledged

  # Why: Core prose path — markdown is chunked heading-aware, embedded, and stored as chunks
  @key-example @smoke
  Scenario: A markdown episode is chunked, embedded, and stored as chunks under the project chunk namespace
    Given a MemoryEpisodeV1 whose content format is markdown for project "guardkit"
    When the consumer receives the episode
    Then the body should be split into heading-aware chunks
    And each chunk should be embedded and stored under the project chunk namespace
    And the episode should be acknowledged

  # Why: Plain text takes the same chunk+embed path as markdown (RD-7 — unstructured = chunk+embed)
  @key-example
  Scenario: A plain text episode is chunked and embedded on the same path as markdown
    Given a MemoryEpisodeV1 whose content format is plain text
    When the consumer receives the episode
    Then the body should be chunked and embedded and stored as chunks
    And the episode should be acknowledged

  # Why: Content format is the routing key — it alone selects which write path runs
  @key-example @smoke
  Scenario Outline: The episode content format selects the write path
    Given a MemoryEpisodeV1 whose content format is "<format>"
    When the consumer receives the episode
    Then it should be processed by the "<path>" path

    Examples:
      | format   | path       |
      | json     | structured |
      | markdown | chunk      |
      | text     | chunk      |

  # Why: The headline acceptance criterion — a mixed batch produces typed records and chunks together
  @key-example @smoke
  Scenario: A mixed batch of structured and prose episodes yields typed records and chunks
    Given 3 structured JSON episodes for known payload types
    And 2 markdown episodes
    When the consumer processes all five episodes
    Then 3 typed records should exist
    And the markdown episodes should produce one or more chunks
    And all five episodes should be acknowledged

  # Why: Ack-after-commit is what makes at-least-once delivery safe — nothing is acked until it is durable
  # [ASSUMPTION: confidence=medium] An episode is acknowledged only after its write has durably committed to the store
  @key-example @smoke
  Scenario: An episode is acknowledged only after it is durably stored
    Given a MemoryEpisodeV1 ready to process
    When the consumer processes the episode
    Then the episode should not be acknowledged before its write has committed
    And it should be acknowledged once the write has committed

  # Why: Provenance must survive ingestion — every chunk traces back to its source episode
  @key-example
  Scenario: Each stored chunk carries the source reference and project of its originating episode
    Given a markdown episode for project "guardkit" with a known source reference
    When the consumer processes the episode
    Then every resulting chunk should record that source reference
    And every resulting chunk should be stored in the "guardkit" project namespace

━━ GROUP B: Boundary Conditions (6 scenarios) ━━

  # Why: Chunk-count boundary — content below, at, and above one chunk produces the expected chunk counts
  # [ASSUMPTION: confidence=medium] Target chunk size is approximately 1000 tokens (OD-1 starting value)
  @boundary
  Scenario Outline: Prose content produces a chunk count proportional to its size
    Given a markdown episode whose body is <size>
    When the consumer processes the episode
    Then it should produce <chunks> chunk(s)

    Examples:
      | size                          | chunks   |
      | well under one chunk          | 1        |
      | exactly one chunk             | 1        |
      | just over one chunk           | 2        |
      | several chunks long           | multiple |

  # Why: Just-inside overlap — adjacent chunks must share overlapping content so meaning is not severed at a cut
  # [ASSUMPTION: confidence=medium] Adjacent chunks overlap by approximately 15% of chunk size (OD-1 starting value)
  @boundary
  Scenario: Adjacent chunks of a multi-chunk document share overlapping content
    Given a markdown episode long enough to span at least two chunks
    When the consumer processes the episode
    Then each chunk after the first should begin with content overlapping the previous chunk

  # Why: Heading awareness — a chunk boundary should prefer a heading break over splitting mid-section
  @boundary
  Scenario: Chunk boundaries prefer heading breaks over splitting a section mid-sentence
    Given a markdown episode with multiple headings and sections
    When the consumer processes the episode
    Then chunk boundaries should fall at heading breaks where possible
    And no heading line should be separated from the section it introduces

  # Why: Empty-body boundary — an episode with no usable content produces no chunks but is still accounted for
  # [ASSUMPTION: confidence=low] An episode whose body is empty or whitespace-only produces zero chunks and is acknowledged, not parked
  @boundary
  Scenario: A prose episode with an empty body produces no chunks and is acknowledged
    Given a markdown episode whose body is empty
    When the consumer processes the episode
    Then no chunk should be created
    And the episode should be acknowledged

  # Why: Just-inside redelivery — a transient failure short of the delivery limit is retried, not parked
  # [ASSUMPTION: confidence=low] The consumer parks an episode only after max_deliver attempts; max_deliver is 5
  @boundary
  Scenario: An episode that has failed fewer than the delivery limit is redelivered, not parked
    Given an episode that has been delivered 4 times without being acknowledged
    When it is delivered once more and processing succeeds
    Then the episode should be acknowledged
    And it should not be sent to the dead-letter subject

  # Why: Just-outside redelivery — the attempt that reaches the limit parks the episode
  @boundary @negative
  Scenario: An episode that reaches the delivery limit is parked on the dead-letter subject
    Given an episode that keeps failing on every delivery
    When it has been delivered the maximum number of times
    Then the episode should be sent to the dead-letter subject
    And the consumer should continue processing other episodes

━━ GROUP C: Negative Cases (6 scenarios) ━━

  # Why: A poison body that can never parse is parked — retrying it forever would stall the stream
  # [ASSUMPTION: confidence=medium] A body that cannot be parsed is a deterministic (poison) failure routed to the dead-letter subject
  @negative
  Scenario: An episode whose body cannot be parsed is routed to the dead-letter subject
    Given a MemoryEpisodeV1 whose body is not parseable for its declared content format
    When the consumer receives the episode
    Then the episode should be routed to the dead-letter subject with a recorded reason
    And the consumer should continue processing other episodes

  # Why: An unknown payload type cannot be dispatched — registry has no silent fallback (FEAT-MEM-02 contract)
  @negative
  Scenario: A structured episode declaring an unknown payload type is parked
    Given a structured JSON episode declaring a payload type the registry does not know
    When the consumer receives the episode
    Then no record should be written
    And the episode should be routed to the dead-letter subject naming the unknown payload type

  # Why: A structured body missing a required field is a deterministic validation failure, never a write
  @negative
  Scenario: A structured episode that fails payload validation is parked without a write
    Given a structured JSON episode missing a field its payload type requires
    When the consumer receives the episode
    Then no record should be written
    And the episode should be routed to the dead-letter subject

  # Why: An unrecognized content format has no path — it must be parked, not guessed at
  # [ASSUMPTION: confidence=low] The only recognized content formats are json, markdown, and text
  @negative
  Scenario: An episode with an unrecognized content format is parked
    Given a MemoryEpisodeV1 whose content format is "yaml"
    When the consumer receives the episode
    Then no record or chunk should be created
    And the episode should be routed to the dead-letter subject

  # Why: Underscores-everywhere — a hyphenated project is rejected before any write, on both paths
  @negative
  Scenario: An episode whose project contains a hyphen is parked before any write
    Given a MemoryEpisodeV1 for project "guard-kit"
    When the consumer receives the episode
    Then no record or chunk should be created
    And the episode should be routed to the dead-letter subject

  # Why: Transient failures must be retried, never parked — distinguishing them from poison is the core ack/nak decision
  # [ASSUMPTION: confidence=medium] A transient downstream failure causes a negative-acknowledge and redelivery, not dead-lettering
  @negative
  Scenario: A transient downstream failure causes redelivery rather than dead-lettering
    Given the embedding service is temporarily unavailable
    When the consumer processes a markdown episode
    Then the episode should be negatively acknowledged for redelivery
    And the episode should not be sent to the dead-letter subject

━━ GROUP D: Edge Cases (7 scenarios) ━━

  # Why: AC — redelivery of an acked structured episode changes nothing (writer natural-key upsert is the ledger)
  @edge-case @regression
  Scenario: Redelivery of an already-stored structured episode changes nothing
    Given a structured episode that has already been processed and stored
    When the same episode is delivered again
    Then only one record should exist for that payload's natural key
    And the redelivery should leave the stored record unchanged

  # Why: AC — redelivery of an acked prose episode produces no duplicate chunks (episode_id keys are the ledger)
  # [ASSUMPTION: confidence=medium] Chunk identity is derived from the episode_id plus chunk position, making re-chunking idempotent
  @edge-case @regression
  Scenario: Redelivery of an already-chunked prose episode creates no duplicate chunks
    Given a markdown episode that has already been chunked and stored
    When the same episode is delivered again
    Then the chunk set for that episode should be identical to before
    And no duplicate chunk should be created

  # Why: AC — a poison episode is parked after the delivery limit and the consumer keeps going
  @edge-case @regression
  Scenario: A poison episode is parked and the consumer keeps processing the episodes behind it
    Given a poison episode at the head of the stream followed by valid episodes
    When the consumer works through the stream
    Then the poison episode should end up on the dead-letter subject
    And every valid episode behind it should be processed and acknowledged

  # Why: The at-least-once seam — a crash after commit but before ack must redeliver to an idempotent no-op
  @edge-case @regression
  Scenario: A crash after the write commits but before the ack results in an idempotent redelivery
    Given an episode whose write commits but whose acknowledgement is lost to a crash
    When the episode is redelivered after restart
    Then no second record or duplicate chunk should be created
    And the episode should then be acknowledged

  # Why: AC — no language model touches the ingestion path (the whole thesis, as an enforceable check)
  @edge-case @regression @negative
  Scenario: Ingesting episodes makes no language-model or chat-completion calls
    Given a batch of structured and prose episodes
    When the consumer ingests the entire batch
    Then no language-model or chat-completion request should be made on the write path

  # Why: Structured and prose episodes are independent — one path failing must not block the other
  @edge-case
  Scenario: A failing prose episode does not block structured episodes interleaved with it
    Given a stream interleaving a failing markdown episode with valid structured episodes
    When the consumer processes the stream
    Then the structured episodes should be stored and acknowledged
    And the failing markdown episode should be handled by its own ack or dead-letter decision

  # Why: Chunk-write atomicity — a mid-document failure must not leave a half-chunked episode behind
  # [ASSUMPTION: confidence=low] A prose episode's chunks are committed so that a partial failure leaves no incomplete chunk set for that episode_id
  @edge-case
  Scenario: A prose episode interrupted partway through chunking leaves no partial chunk set
    Given a markdown episode whose chunk writes fail partway through
    When the episode is redelivered and reprocessed
    Then the stored chunk set for that episode should be complete
    And no orphaned partial chunks should remain for that episode

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: 26 scenarios across 4 groups
Inferred assumptions: 11 (will be resolved in Phase 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Now the curation step:


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURATION: Review each group
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For each group:
  [A] Accept   [R] Reject   [M] Modify (give changes inline)
  [+] Add (describe scenario)   [?] Defer (exclude from output)

Fast path: type "A A A A" to accept all four groups.

GROUP A — Key Examples (7 scenarios): _
GROUP B — Boundary Conditions (6 scenarios): _
GROUP C — Negative Cases (6 scenarios): _
GROUP D — Edge Cases (7 scenarios): _
A few notes that may guide your curation:

Group B chunking params (1000 tokens, 15% overlap, heading-aware) come from OD-1 in the build plan, marked there as starting values to tune on probe-set evidence — I've flagged them medium. If you have firmer numbers, [M] the group.
DLQ / max_deliver semantics (Group B/C) are inherited from relay scope D5/D9, which I couldn't read (sibling repo). max_deliver=5, the dead-letter subject name, and the transient-vs-poison split are my best inferences — these are the lowest-confidence items and the prime candidates for [M].
After curation I'll offer Phase 4 edge-case expansion (security/injection in chunked content, concurrency on the same episode_id, integration-boundary failures) — I deliberately kept those out of Group D so the core delivery semantics stay reviewable on their own.
How would you like to curate the four groups?

phase-core-build-plan.md
A A A A
All four groups accepted. Now Phase 4: Edge Case Expansion.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDGE CASE EXPANSION (optional)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
I've identified 6 additional scenarios covering security, concurrency, and integration boundaries — deliberately held back from Group D so the core delivery semantics stayed reviewable:

Security / injection (2)

A markdown body containing injection-shaped text (DB commands, prompt-injection strings) is chunked and stored verbatim and stays inert.
An episode whose source_ref or episode_id carries key-delimiter or path-shaped text cannot forge a chunk identity in another namespace.
Concurrency (2)

The same episode delivered twice concurrently (two consumer deliveries racing) converges to one record / one chunk set.
Two different episodes for the same project processed concurrently each write independently without cross-contaminating namespaces.
Integration boundaries (2)

The store becomes unreachable mid-batch → in-flight episodes are negatively acknowledged and redelivered, none silently lost (zero-capture-loss invariant).
The embedding service returns wrong-dimension vectors → the chunk write fails loudly and the episode is parked rather than storing a malformed chunk.

[Y] Yes    — show all 6 and curate them (A/R/M/+/? per group)
[S] Sample — show 2 in full, then decide
[N] No     — skip to Phase 5 (Assumption Resolution)

Your choice [Y/S/N]: _
Y
Here are the 6 expansion scenarios in full.


━━ EDGE CASE EXPANSION: Security / Injection (2) ━━

  # Why: Memory content is data, never instructions — hostile prose must round-trip inert through chunking
  @edge-case @negative
  Scenario: A prose episode containing injection-shaped text is chunked and stored verbatim and stays inert
    Given a markdown episode whose body contains database commands and prompt-injection text
    When the consumer chunks and stores the episode
    Then the stored chunks should contain that text byte-for-byte as written
    And no command in the content should be executed
    And no other record or namespace should be affected

  # Why: Chunk identity is derived data — delimiter or path text in episode metadata must not forge identity elsewhere
  @edge-case @negative
  Scenario: An episode whose identifiers carry delimiter or path text cannot forge a chunk identity in another namespace
    Given a markdown episode for project "guardkit" whose episode reference carries key-delimiter or path-shaped text
    When the consumer processes the episode
    Then every resulting chunk should be confined to the "guardkit" chunk namespace
    And no chunk should be written outside that project namespace

━━ EDGE CASE EXPANSION: Concurrency (2) ━━

  # Why: At-least-once delivery can race the same episode against itself — both deliveries must converge to one outcome
  @edge-case @regression
  Scenario: The same episode delivered twice concurrently converges to a single stored outcome
    Given the same episode delivered twice at the same time under at-least-once delivery
    When the consumer processes both deliveries concurrently
    Then exactly one record or one chunk set should exist for that episode
    And no duplicate should ever be created

  # Why: Concurrent episodes for one project must not cross-contaminate each other's writes
  @edge-case
  Scenario: Two different episodes for the same project processed concurrently write independently
    Given two different episodes for project "guardkit" arriving at the same time
    When the consumer processes both concurrently
    Then each episode should produce its own record or chunk set
    And neither episode's content should appear in the other's stored output

━━ EDGE CASE EXPANSION: Integration Boundaries (2) ━━

  # Why: Zero capture loss is the founding invariant — a store outage must redeliver, never silently drop in-flight work
  @edge-case @negative @regression
  Scenario: A store outage mid-batch redelivers in-flight episodes rather than losing them
    Given a batch of episodes being processed when the store becomes unreachable
    When the in-flight writes fail
    Then the affected episodes should be negatively acknowledged for redelivery
    And no in-flight episode should be acknowledged as stored
    And every episode should later be either stored or recorded on the dead-letter subject

  # Why: A wrong-dimension embedding must fail loudly, never persist a malformed chunk
  @edge-case @negative
  Scenario: An embedding with the wrong dimensions fails the chunk write and parks the episode
    Given the store is configured for its fixed embedding dimensions
    When the consumer stores a chunk whose embedding has a different number of dimensions
    Then the chunk write should fail with a dimension mismatch
    And no malformed chunk should be stored

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURATION: Edge case expansion (same A/R/M/+/? actions)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Fast path: type "A A A" to accept all three expansion groups.

EXPANSION — Security / Injection (2 scenarios): _
EXPANSION — Concurrency (2 scenarios): _
EXPANSION — Integration Boundaries (2 scenarios): _
A A A
All expansion groups accepted — 32 scenarios total. Now Phase 5: Assumption Resolution.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSUMPTION RESOLUTION (11 items)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Press Enter to accept the default, or type the actual value.

[1] Recognized content formats
    Proposed: json, markdown, text   Confidence: medium
    Basis: Build plan FEAT-MEM-04 names json→structured and markdown/text→chunk; "json" selects the structured path
    Accept or enter value: _

[2] Target chunk size
    Proposed: ~1000 tokens   Confidence: medium
    Basis: OD-1 starting value ("~1K-token chunks"), to be tuned on probe-set evidence
    Accept or enter value: _

[3] Chunk overlap
    Proposed: ~15% of chunk size   Confidence: medium
    Basis: OD-1 starting value ("15% overlap")
    Accept or enter value: _

[4] Heading-aware splitting rule
    Proposed: prefer heading breaks as chunk boundaries; never separate a heading from its section
    Confidence: medium   Basis: OD-1 ("heading-aware"); exact rule not specified
    Accept or enter value: _

[5] Delivery limit before dead-lettering (max_deliver)
    Proposed: 5   Confidence: low
    Basis: Relay scope D5/D9 (sibling repo, unreadable here); common JetStream default
    Accept or enter value: _

[6] Dead-letter subject
    Proposed: a dedicated DLQ subject (e.g. MEMORY.dlq)   Confidence: low
    Basis: AC says "malformed body → DLQ subject"; exact name in relay scope D9
    Accept or enter value: _

[7] Chunk namespace tuple
    Proposed: ("fleet_memory", project, "chunk")   Confidence: high
    Basis: Stated verbatim in build plan FEAT-MEM-04
    Accept or enter value: _

[8] Chunk idempotency key
    Proposed: derived from episode_id + chunk position   Confidence: medium
    Basis: Build plan — "chunk path uses episode_id keys" (relay O3 resolved)
    Accept or enter value: _

[9] Acknowledgement timing
    Proposed: ack only after the write durably commits   Confidence: medium
    Basis: AC "redelivery of an acked episode changes nothing" implies commit-before-ack
    Accept or enter value: _

[10] Transient vs. poison failure handling
     Proposed: transient (store/embed down) → nak + redeliver; deterministic (parse/validation/unknown-type) → DLQ
     Confidence: medium   Basis: AC distinguishes "malformed → DLQ after max_deliver, consumer continues"
     Accept or enter value: _

[11] Durable consumer / stream identity
     Proposed: a named durable consumer bound to the MEMORY stream   Confidence: high
     Basis: Build plan + AC name the MEMORY stream and a durable consumer explicitly
     Accept or enter value: _
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can reply per-item (e.g. 5: 3, 6: MEMORY.DLQ.>) or accept all to take every default as proposed.

accept all
All assumptions accepted at proposed defaults. Executing Phase 6: Output Generation.

Bash Get ISO 8601 UTC timestamp
IN
date -u +"%Y-%m-%dT%H:%M:%SZ"

OUT
2026-06-13T11:04:22Z
Write relay-integration.feature
323 lines
# Generated by /feature-spec
# Feature: Relay Integration (FEAT-MEM-04)
# Stack: python
# Assumptions: 11 (see relay-integration_assumptions.yaml)
# Generated: 2026-06-13T11:04:22Z
#
# Context sources: docs/research/ideas/phase-core-build-plan.md (FEAT-MEM-04),
# docs/research/ideas/phase-core-scope.md, features/typed-payload-registry/typed-payload-registry.feature,
# features/deterministic-writer/deterministic-writer.feature, src/fleet_memory/store.py, src/fleet_memory/embed.py
#
# Relay ack/nak/DLQ semantics (D5/D9) and max_deliver inherit from the
# nats-infrastructure memory-relay scope, which is not readable from this repo;
# those values are carried here as low-confidence assumptions for Coach review.
#
# Background applies: every scenario assumes the durable consumer is subscribed
# to the MEMORY stream with the registry, writer, embedding service, and store available.

@relay-integration
Feature: Relay Integration
  As the fleet-memory relay consumer on the MEMORY stream
  I want every published MemoryEpisodeV1 routed by its content format — structured payloads through the registry to the deterministic writer, prose chunked and embedded — and acknowledged only once durably stored, with poison episodes parked and redeliveries made inert
  So that capture is fire-and-forget and lossless, no episode is silently dropped, no language model touches the write path, and at-least-once redelivery can never duplicate a memory

  Background:
    Given the relay consumer is subscribed to the MEMORY stream as a durable consumer
    And the typed payload registry and deterministic writer are available
    And the embedding service and store are available

  # ───────────────────────── Key examples ────────────────────────────

  # Why: Core structured path — content_format json dispatches through the registry to the writer
  @key-example @smoke
  Scenario: A structured JSON episode is dispatched through the registry to the deterministic writer
    Given a MemoryEpisodeV1 whose content format is structured JSON for a known payload type
    When the consumer receives the episode
    Then the payload should be dispatched through the registry to the deterministic writer
    And a typed record for that payload should exist in the project namespace
    And the episode should be acknowledged

  # Why: Core prose path — markdown is chunked heading-aware, embedded, and stored as chunks
  @key-example @smoke
  Scenario: A markdown episode is chunked, embedded, and stored as chunks under the project chunk namespace
    Given a MemoryEpisodeV1 whose content format is markdown for project "guardkit"
    When the consumer receives the episode
    Then the body should be split into heading-aware chunks
    And each chunk should be embedded and stored under the project chunk namespace
    And the episode should be acknowledged

  # Why: Plain text takes the same chunk+embed path as markdown (RD-7 — unstructured = chunk+embed)
  @key-example
  Scenario: A plain text episode is chunked and embedded on the same path as markdown
    Given a MemoryEpisodeV1 whose content format is plain text
    When the consumer receives the episode
    Then the body should be chunked and embedded and stored as chunks
    And the episode should be acknowledged

  # Why: Content format is the routing key — it alone selects which write path runs
  @key-example @smoke
  Scenario Outline: The episode content format selects the write path
    Given a MemoryEpisodeV1 whose content format is "<format>"
    When the consumer receives the episode
    Then it should be processed by the "<path>" path

    Examples:
      | format   | path       |
      | json     | structured |
      | markdown | chunk      |
      | text     | chunk      |

  # Why: The headline acceptance criterion — a mixed batch produces typed records and chunks together
  @key-example @smoke
  Scenario: A mixed batch of structured and prose episodes yields typed records and chunks
    Given 3 structured JSON episodes for known payload types
    And 2 markdown episodes
    When the consumer processes all five episodes
    Then 3 typed records should exist
    And the markdown episodes should produce one or more chunks
    And all five episodes should be acknowledged

  # Why: Ack-after-commit is what makes at-least-once delivery safe — nothing is acked until it is durable
  # [ASSUMPTION: confidence=medium] An episode is acknowledged only after its write has durably committed to the store
  @key-example @smoke
  Scenario: An episode is acknowledged only after it is durably stored
    Given a MemoryEpisodeV1 ready to process
    When the consumer processes the episode
    Then the episode should not be acknowledged before its write has committed
    And it should be acknowledged once the write has committed

  # Why: Provenance must survive ingestion — every chunk traces back to its source episode
  @key-example
  Scenario: Each stored chunk carries the source reference and project of its originating episode
    Given a markdown episode for project "guardkit" with a known source reference
    When the consumer processes the episode
    Then every resulting chunk should record that source reference
    And every resulting chunk should be stored in the "guardkit" project namespace

  # ───────────────────── Boundary conditions ─────────────────────────

  # Why: Chunk-count boundary — content below, at, and above one chunk produces the expected chunk counts
  # [ASSUMPTION: confidence=medium] Target chunk size is approximately 1000 tokens (OD-1 starting value)
  @boundary
  Scenario Outline: Prose content produces a chunk count proportional to its size
    Given a markdown episode whose body is <size>
    When the consumer processes the episode
    Then it should produce <chunks> chunk(s)

    Examples:
      | size                 | chunks   |
      | well under one chunk | 1        |
      | exactly one chunk    | 1        |
      | just over one chunk  | 2        |
      | several chunks long  | multiple |

  # Why: Just-inside overlap — adjacent chunks must share overlapping content so meaning is not severed at a cut
  # [ASSUMPTION: confidence=medium] Adjacent chunks overlap by approximately 15% of chunk size (OD-1 starting value)
  @boundary
  Scenario: Adjacent chunks of a multi-chunk document share overlapping content
    Given a markdown episode long enough to span at least two chunks
    When the consumer processes the episode
    Then each chunk after the first should begin with content overlapping the previous chunk

  # Why: Heading awareness — a chunk boundary should prefer a heading break over splitting mid-section
  @boundary
  Scenario: Chunk boundaries prefer heading breaks over splitting a section mid-sentence
    Given a markdown episode with multiple headings and sections
    When the consumer processes the episode
    Then chunk boundaries should fall at heading breaks where possible
    And no heading line should be separated from the section it introduces

  # Why: Empty-body boundary — an episode with no usable content produces no chunks but is still accounted for
  # [ASSUMPTION: confidence=low] An episode whose body is empty or whitespace-only produces zero chunks and is acknowledged, not parked
  @boundary
  Scenario: A prose episode with an empty body produces no chunks and is acknowledged
    Given a markdown episode whose body is empty
    When the consumer processes the episode
    Then no chunk should be created
    And the episode should be acknowledged

  # Why: Just-inside redelivery — a transient failure short of the delivery limit is retried, not parked
  # [ASSUMPTION: confidence=low] The consumer parks an episode only after max_deliver attempts; max_deliver is 5
  @boundary
  Scenario: An episode that has failed fewer than the delivery limit is redelivered, not parked
    Given an episode that has been delivered 4 times without being acknowledged
    When it is delivered once more and processing succeeds
    Then the episode should be acknowledged
    And it should not be sent to the dead-letter subject

  # Why: Just-outside redelivery — the attempt that reaches the limit parks the episode
  @boundary @negative
  Scenario: An episode that reaches the delivery limit is parked on the dead-letter subject
    Given an episode that keeps failing on every delivery
    When it has been delivered the maximum number of times
    Then the episode should be sent to the dead-letter subject
    And the consumer should continue processing other episodes

  # ─────────────────────── Negative cases ────────────────────────────

  # Why: A poison body that can never parse is parked — retrying it forever would stall the stream
  # [ASSUMPTION: confidence=medium] A body that cannot be parsed is a deterministic (poison) failure routed to the dead-letter subject
  @negative
  Scenario: An episode whose body cannot be parsed is routed to the dead-letter subject
    Given a MemoryEpisodeV1 whose body is not parseable for its declared content format
    When the consumer receives the episode
    Then the episode should be routed to the dead-letter subject with a recorded reason
    And the consumer should continue processing other episodes

  # Why: An unknown payload type cannot be dispatched — registry has no silent fallback (FEAT-MEM-02 contract)
  @negative
  Scenario: A structured episode declaring an unknown payload type is parked
    Given a structured JSON episode declaring a payload type the registry does not know
    When the consumer receives the episode
    Then no record should be written
    And the episode should be routed to the dead-letter subject naming the unknown payload type

  # Why: A structured body missing a required field is a deterministic validation failure, never a write
  @negative
  Scenario: A structured episode that fails payload validation is parked without a write
    Given a structured JSON episode missing a field its payload type requires
    When the consumer receives the episode
    Then no record should be written
    And the episode should be routed to the dead-letter subject

  # Why: An unrecognized content format has no path — it must be parked, not guessed at
  # [ASSUMPTION: confidence=low] The only recognized content formats are json, markdown, and text
  @negative
  Scenario: An episode with an unrecognized content format is parked
    Given a MemoryEpisodeV1 whose content format is "yaml"
    When the consumer receives the episode
    Then no record or chunk should be created
    And the episode should be routed to the dead-letter subject

  # Why: Underscores-everywhere — a hyphenated project is rejected before any write, on both paths
  @negative
  Scenario: An episode whose project contains a hyphen is parked before any write
    Given a MemoryEpisodeV1 for project "guard-kit"
    When the consumer receives the episode
    Then no record or chunk should be created
    And the episode should be routed to the dead-letter subject

  # Why: Transient failures must be retried, never parked — distinguishing them from poison is the core ack/nak decision
  # [ASSUMPTION: confidence=medium] A transient downstream failure causes a negative-acknowledge and redelivery, not dead-lettering
  @negative
  Scenario: A transient downstream failure causes redelivery rather than dead-lettering
    Given the embedding service is temporarily unavailable
    When the consumer processes a markdown episode
    Then the episode should be negatively acknowledged for redelivery
    And the episode should not be sent to the dead-letter subject

  # ──────────────────────── Edge cases ───────────────────────────────

  # Why: AC — redelivery of an acked structured episode changes nothing (writer natural-key upsert is the ledger)
  @edge-case @regression
  Scenario: Redelivery of an already-stored structured episode changes nothing
    Given a structured episode that has already been processed and stored
    When the same episode is delivered again
    Then only one record should exist for that payload's natural key
    And the redelivery should leave the stored record unchanged

  # Why: AC — redelivery of an acked prose episode produces no duplicate chunks (episode_id keys are the ledger)
  # [ASSUMPTION: confidence=medium] Chunk identity is derived from the episode_id plus chunk position, making re-chunking idempotent
  @edge-case @regression
  Scenario: Redelivery of an already-chunked prose episode creates no duplicate chunks
    Given a markdown episode that has already been chunked and stored
    When the same episode is delivered again
    Then the chunk set for that episode should be identical to before
    And no duplicate chunk should be created

  # Why: AC — a poison episode is parked after the delivery limit and the consumer keeps going
  @edge-case @regression
  Scenario: A poison episode is parked and the consumer keeps processing the episodes behind it
    Given a poison episode at the head of the stream followed by valid episodes
    When the consumer works through the stream
    Then the poison episode should end up on the dead-letter subject
    And every valid episode behind it should be processed and acknowledged

  # Why: The at-least-once seam — a crash after commit but before ack must redeliver to an idempotent no-op
  @edge-case @regression
  Scenario: A crash after the write commits but before the ack results in an idempotent redelivery
    Given an episode whose write commits but whose acknowledgement is lost to a crash
    When the episode is redelivered after restart
    Then no second record or duplicate chunk should be created
    And the episode should then be acknowledged

  # Why: AC — no language model touches the ingestion path (the whole thesis, as an enforceable check)
  @edge-case @regression @negative
  Scenario: Ingesting episodes makes no language-model or chat-completion calls
    Given a batch of structured and prose episodes
    When the consumer ingests the entire batch
    Then no language-model or chat-completion request should be made on the write path

  # Why: Structured and prose episodes are independent — one path failing must not block the other
  @edge-case
  Scenario: A failing prose episode does not block structured episodes interleaved with it
    Given a stream interleaving a failing markdown episode with valid structured episodes
    When the consumer processes the stream
    Then the structured episodes should be stored and acknowledged
    And the failing markdown episode should be handled by its own ack or dead-letter decision

  # Why: Chunk-write atomicity — a mid-document failure must not leave a half-chunked episode behind
  # [ASSUMPTION: confidence=low] A prose episode's chunks are committed so that a partial failure leaves no incomplete chunk set for that episode_id
  @edge-case
  Scenario: A prose episode interrupted partway through chunking leaves no partial chunk set
    Given a markdown episode whose chunk writes fail partway through
    When the episode is redelivered and reprocessed
    Then the stored chunk set for that episode should be complete
    And no orphaned partial chunks should remain for that episode

  # ──────────────── Edge cases — security / injection ─────────────────

  # Why: Memory content is data, never instructions — hostile prose must round-trip inert through chunking
  @edge-case @negative
  Scenario: A prose episode containing injection-shaped text is chunked and stored verbatim and stays inert
    Given a markdown episode whose body contains database commands and prompt-injection text
    When the consumer chunks and stores the episode
    Then the stored chunks should contain that text byte-for-byte as written
    And no command in the content should be executed
    And no other record or namespace should be affected

  # Why: Chunk identity is derived data — delimiter or path text in episode metadata must not forge identity elsewhere
  @edge-case @negative
  Scenario: An episode whose identifiers carry delimiter or path text cannot forge a chunk identity in another namespace
    Given a markdown episode for project "guardkit" whose episode reference carries key-delimiter or path-shaped text
    When the consumer processes the episode
    Then every resulting chunk should be confined to the "guardkit" chunk namespace
    And no chunk should be written outside that project namespace

  # ──────────────────── Edge cases — concurrency ──────────────────────

  # Why: At-least-once delivery can race the same episode against itself — both deliveries must converge to one outcome
  @edge-case @regression
  Scenario: The same episode delivered twice concurrently converges to a single stored outcome
    Given the same episode delivered twice at the same time under at-least-once delivery
    When the consumer processes both deliveries concurrently
    Then exactly one record or one chunk set should exist for that episode
    And no duplicate should ever be created

  # Why: Concurrent episodes for one project must not cross-contaminate each other's writes
  @edge-case
  Scenario: Two different episodes for the same project processed concurrently write independently
    Given two different episodes for project "guardkit" arriving at the same time
    When the consumer processes both concurrently
    Then each episode should produce its own record or chunk set
    And neither episode's content should appear in the other's stored output

  # ─────────────── Edge cases — integration boundaries ────────────────

  # Why: Zero capture loss is the founding invariant — a store outage must redeliver, never silently drop in-flight work
  @edge-case @negative @regression
  Scenario: A store outage mid-batch redelivers in-flight episodes rather than losing them
    Given a batch of episodes being processed when the store becomes unreachable
    When the in-flight writes fail
    Then the affected episodes should be negatively acknowledged for redelivery
    And no in-flight episode should be acknowledged as stored
    And every episode should later be either stored or recorded on the dead-letter subject

  # Why: A wrong-dimension embedding must fail loudly, never persist a malformed chunk
  @edge-case @negative
  Scenario: An embedding with the wrong dimensions fails the chunk write and parks the episode
    Given the store is configured for its fixed embedding dimensions
    When the consumer stores a chunk whose embedding has a different number of dimensions
    Then the chunk write should fail with a dimension mismatch
    And no malformed chunk should be stored
Write relay-integration_assumptions.yaml
86 lines
# Assumptions manifest for relay-integration.feature
# Generated by /feature-spec

feature: "Relay Integration"
generated: "2026-06-13T11:04:22Z"
stack: "python"
review_required: true

assumptions:
  - id: "ASSUM-001"
    scenario: "The episode content format selects the write path"
    assumption: "Recognized content formats are json, markdown, and text; json selects the structured path, markdown and text the chunk path"
    confidence: medium
    basis: "Build plan FEAT-MEM-04 names json->structured and markdown/text->chunk; enum membership not frozen in a readable schema here"
    human_response: "confirmed"

  - id: "ASSUM-002"
    scenario: "Prose content produces a chunk count proportional to its size"
    assumption: "Target chunk size is approximately 1000 tokens"
    confidence: medium
    basis: "OD-1 starting value (~1K-token chunks), explicitly marked for tuning on probe-set evidence"
    human_response: "confirmed"

  - id: "ASSUM-003"
    scenario: "Adjacent chunks of a multi-chunk document share overlapping content"
    assumption: "Adjacent chunks overlap by approximately 15% of chunk size"
    confidence: medium
    basis: "OD-1 starting value (15% overlap), marked for tuning"
    human_response: "confirmed"

  - id: "ASSUM-004"
    scenario: "Chunk boundaries prefer heading breaks over splitting a section mid-sentence"
    assumption: "Chunking prefers heading breaks as boundaries and never separates a heading from the section it introduces"
    confidence: medium
    basis: "OD-1 specifies heading-aware chunking; the exact splitting rule is not specified"
    human_response: "confirmed"

  - id: "ASSUM-005"
    scenario: "An episode that has failed fewer than the delivery limit is redelivered, not parked"
    assumption: "The consumer parks an episode only after max_deliver attempts; max_deliver is 5"
    confidence: low
    basis: "Relay scope D5/D9 lives in the sibling nats-infrastructure repo and is not readable here; 5 is a common JetStream default"
    human_response: "confirmed"

  - id: "ASSUM-006"
    scenario: "An episode that reaches the delivery limit is parked on the dead-letter subject"
    assumption: "Failed episodes are routed to a dedicated dead-letter (DLQ) subject"
    confidence: low
    basis: "AC states 'malformed body -> DLQ subject after max_deliver'; the exact subject name is defined in relay scope D9"
    human_response: "confirmed"

  - id: "ASSUM-007"
    scenario: "A markdown episode is chunked, embedded, and stored as chunks under the project chunk namespace"
    assumption: "Chunks are stored under the namespace tuple (fleet_memory, project, chunk)"
    confidence: high
    basis: "Stated verbatim in build plan FEAT-MEM-04"
    human_response: "confirmed"

  - id: "ASSUM-008"
    scenario: "Redelivery of an already-chunked prose episode creates no duplicate chunks"
    assumption: "Chunk identity is derived from the episode_id plus chunk position, making re-chunking idempotent"
    confidence: medium
    basis: "Build plan: 'chunk path uses episode_id keys' (relay O3 resolved); the position component is inferred"
    human_response: "confirmed"

  - id: "ASSUM-009"
    scenario: "An episode is acknowledged only after it is durably stored"
    assumption: "An episode is acknowledged only after its write has durably committed to the store"
    confidence: medium
    basis: "AC 'redelivery of an acked episode changes nothing' implies commit-before-ack ordering"
    human_response: "confirmed"

  - id: "ASSUM-010"
    scenario: "A transient downstream failure causes redelivery rather than dead-lettering"
    assumption: "Transient downstream failures (store/embedding unavailable) cause negative-acknowledge and redelivery; deterministic failures (parse, validation, unknown type, unrecognized format) are routed to the dead-letter subject"
    confidence: medium
    basis: "AC distinguishes 'malformed -> DLQ after max_deliver, consumer continues' from retryable conditions; the transient/poison split is the core ack/nak decision in relay scope D5/D9"
    human_response: "confirmed"

  - id: "ASSUM-011"
    scenario: "A structured JSON episode is dispatched through the registry to the deterministic writer"
    assumption: "The consumer is a named durable consumer bound to the MEMORY stream"
    confidence: high
    basis: "Build plan and AC name the MEMORY stream and a durable consumer explicitly"
    human_response: "confirmed"
Write relay-integration_summary.md
65 lines
# Feature Spec Summary: Relay Integration (FEAT-MEM-04)

**Stack**: python
**Generated**: 2026-06-13T11:04:22Z
**Scenarios**: 32 total (5 smoke, 7 regression)
**Assumptions**: 11 total (2 high / 6 medium / 3 low confidence)
**Review required**: Yes

## Scope

The relay consumer is a FastStream durable consumer on the MEMORY stream that
ingests `MemoryEpisodeV1` envelopes published from nats-core. It routes by
`content_format`: structured `json` episodes dispatch through the typed payload
registry (FEAT-MEM-02) to the deterministic writer (FEAT-MEM-03) as typed
records; `markdown` and `text` episodes are split into heading-aware chunks,
embedded, and stored under `(fleet_memory, project, chunk)` with their source
reference. Episodes are acknowledged only after a durable commit; transient
downstream failures are redelivered while poison episodes are parked on the
dead-letter subject after `max_deliver`. Two-layer idempotency — the writer's
natural-key upsert for structured payloads and `episode_id`-derived keys for
chunks — makes at-least-once redelivery inert. No language model is on the
write path.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 7 |
| Boundary conditions (@boundary) | 6 |
| Negative cases (@negative) | 12 |
| Edge cases (@edge-case) | 13 |
| Smoke (@smoke) | 5 |
| Regression (@regression) | 7 |

(A scenario may carry more than one category tag, so counts overlap; the 32
distinct scenarios are grouped as Key 7 / Boundary 6 / Negative 6 / Edge 7 /
Edge-case expansion 6.)

## Deferred Items

None — all four base groups and all three edge-case expansion groups were
accepted during curation.

## Open Assumptions (low confidence)

These need human verification before the spec drives implementation. All three
trace to the relay ack/nak/DLQ contract (D5/D9), which lives in the sibling
`nats-infrastructure` repo and was not readable from this repository:

- **ASSUM-005** — `max_deliver` is 5 before an episode is parked.
- **ASSUM-006** — failed episodes go to a dedicated dead-letter (DLQ) subject (exact name in relay scope D9).
- **ASSUM-013 / empty-body** (ASSUM not numbered as low elsewhere): an empty-body prose episode produces zero chunks and is acknowledged rather than parked — see the `# [ASSUMPTION: confidence=low]` annotation in the feature file.

> Verify ASSUM-005 and ASSUM-006 against the nats-infrastructure memory-relay
> scope (D5/D9) before build, and confirm the empty-body and partial-chunk
> handling (low-confidence annotations in the feature file) reflect the intended
> design.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Relay Integration" \
      --context features/relay-integration/relay-integration_summary.md
Now the mandatory normalization backstop:

Bash Normalize and validate the feature file
IN
python -m installer.core.commands.lib.feature_spec_normalize features/relay-integration/relay-integration.feature; echo "EXIT: $?"

OUT
already clean: features/relay-integration/relay-integration.feature
EXIT: 0
Parser validated the file clean (exit 0).


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Relay Integration (FEAT-MEM-04)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/relay-integration/relay-integration.feature
  features/relay-integration/relay-integration_assumptions.yaml
  features/relay-integration/relay-integration_summary.md

Scenarios: 32 total
  @key-example: 7    @boundary: 6
  @negative: 12      @edge-case: 13
  @smoke: 5          @regression: 7

Assumptions: 11 total
  high: 2   (auto-proceed)
  medium: 6 (Coach review recommended)
  low: 3    (human review required)

REVIEW REQUIRED: 3 low-confidence assumptions need verification
  ASSUM-005  max_deliver = 5 before parking
  ASSUM-006  dead-letter subject name
  + empty-body / partial-chunk handling (low-confidence annotations in-file)
  All three trace to relay scope D5/D9 in the sibling nats-infrastructure repo.

Deferred: 0 groups (all accepted, incl. all 3 edge-case expansion groups)

Next steps:
  Review: features/relay-integration/relay-integration.feature
  Verify D5/D9 against nats-infrastructure/.../memory-relay-scope.md (D5/D9)
  Pass to feature-plan:
    /feature-plan "Relay Integration" \
      --context features/relay-integration/relay-integration_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The spec is the FEAT-MEM-04 consumer that fans MemoryEpisodeV1 into the two existing write surfaces — structured → registry → deterministic writer, prose → heading-aware chunk+embed — with ack-after-commit, transient-vs-poison ack/nak/DLQ handling, and two-layer redelivery idempotency. All four AC bullets from the build plan map to @regression scenarios.

One thing to action before build: the three low-confidence assumptions (max_deliver, DLQ subject name, transient/poison split) all derive from relay scope D5/D9 in the sibling nats-infrastructure repo, which I couldn't read from here. Worth confirming those against that scope doc before /feature-plan so Step 11 links scenarios against the real contract.