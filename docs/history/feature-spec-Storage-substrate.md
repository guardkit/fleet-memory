/feature-spec "Storage substrate: LangGraph AsyncPostgresStore on Postgres 16 + pgvector with nomic-embed-text-v1.5 768-dim embed function via llama-swap :9000; dual deploy targets — deploy/local ephemeral compose for hermetic Mac test gates (random-port, throwaway, used by ALL automated tests incl. AutoBuild) and deploy/nas Synology Container Manager compose for the durable shared instance (backed-up volume, LAN/Tailscale-only 5432); lifespan-managed pool; pydantic-settings DSN/embed config with .env.example profiles for mac-dev-vs-nas; fake-embed unit tests + marker-gated integration tests against the ephemeral instance + one documented smoke against the NAS instance"

I'll run the /feature-spec workflow for this storage-substrate description. Starting with Phase 1: Context Gathering — scanning the repo for stack signals, existing features, and any docs that pin down the values mentioned in the description.

Bash List repo root and all files to 3 levels
IN
ls -la /Users/richardwoollcott/Projects/appmilla_github/fleet-memory; echo '=== FILES (3 levels deep) ==='; find /Users/richardwoollcott/Projects/appmilla_github/fleet-memory -maxdepth 3 -not -path '*/.git/*' -not -path '*/node_modules/*' -type f | sed 's|/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/||' | sort

OUT
total 32
drwxr-xr-x   11 richardwoollcott  staff   352 Jun 12 15:18 .
drwxr-xr-x  173 richardwoollcott  staff  5536 Jun 12 12:43 ..
drwxr-xr-x@  10 richardwoollcott  staff   320 Jun 12 13:01 .claude
drwxr-xr-x   14 richardwoollcott  staff   448 Jun 12 12:50 .git
-rw-r--r--@   1 richardwoollcott  staff  4723 Jun 12 13:02 .gitignore
drwxr-xr-x@   3 richardwoollcott  staff    96 Jun 12 12:48 .guardkit
drwxr-xr-x@   4 richardwoollcott  staff   128 Jun 12 15:28 docs
-rw-r--r--    1 richardwoollcott  staff  1065 Jun 12 12:43 LICENSE
drwxr-xr-x@   2 richardwoollcott  staff    64 Jun 12 15:18 migrations
-rw-r--r--    1 richardwoollcott  staff    38 Jun 12 12:43 README.md
drwxr-xr-x@   7 richardwoollcott  staff   224 Jun 12 12:48 tasks
=== FILES (3 levels deep) ===
.claude/agents/faststream-nats-broker-specialist-ext.md
.claude/agents/faststream-nats-broker-specialist.md
.claude/agents/faststream-test-natsbroker-specialist-ext.md
.claude/agents/faststream-test-natsbroker-specialist.md
.claude/agents/nats-docker-integration-test-specialist-ext.md
.claude/agents/nats-docker-integration-test-specialist.md
.claude/agents/nats-handler-service-separation-specialist-ext.md
.claude/agents/nats-handler-service-separation-specialist.md
.claude/agents/pydantic-nats-schema-specialist-ext.md
.claude/agents/pydantic-nats-schema-specialist.md
.claude/agents/pydantic-settings-config-specialist-ext.md
.claude/agents/pydantic-settings-config-specialist.md
.claude/agents/pytest-asyncio-service-unit-test-specialist-ext.md
.claude/agents/pytest-asyncio-service-unit-test-specialist.md
.claude/CLAUDE.md
.claude/hooks/capture_slash_command.py
.claude/manifest.json
.claude/rules/code-style.md
.claude/rules/testing.md
.claude/settings.json
.gitignore
.guardkit/graphiti.yaml
docs/runbooks/RUNBOOK-nas-postgres-deploy.md
LICENSE
README.md
Read RUNBOOK-nas-postgres-deploy.md
Read testing.md
Read manifest.json
Bash Find all docs/tasks/guardkit files and FEAT-MEM-01 references
IN
find /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tasks /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit -type f | sed 's|/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/||'; echo '=== grep FEAT-MEM-01 / ADR-SP-007 ==='; grep -rln 'FEAT-MEM-01\|ADR-SP-007' /Users/richardwoollcott/Projects/appmilla_github/fleet-memory --include='*.md' --include='*.yaml' -s | sed 's|/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/||'

OUT
.guardkit/graphiti.yaml
docs/runbooks/RUNBOOK-nas-postgres-deploy.md
docs/research/ideas/phase-core-build-plan.md
docs/research/ideas/phase-core-scope.md
=== grep FEAT-MEM-01 / ADR-SP-007 ===
docs/runbooks/RUNBOOK-nas-postgres-deploy.md
docs/research/ideas/phase-core-scope.md
docs/research/ideas/phase-core-build-plan.md
Bash Check line counts of the two research docs
IN
wc -l /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-build-plan.md /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-scope.md

OUT
     278 /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-build-plan.md
     110 /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-scope.md
     388 total
Read phase-core-build-plan.md
Read phase-core-scope.md
Phase 1 complete. The repo scan turned up three documents that pin down most of this feature's facts: the NAS deploy runbook, the Phase CORE build plan (§FEAT-MEM-01 with explicit acceptance criteria), and the scope doc. These upgraded many would-be assumptions to high confidence — settings names (FLEET_MEMORY_PG_DSN/EMBED_URL/EMBED_MODEL), the firewall scope (LAN + tailnet only), the smoke script (deploy/nas/smoke.sh = gates G2–G5), embeddings from GB10 llama-swap :9000 over Tailscale, the underscore identifier rule, and the "NAS powered off" hermeticity criterion.


Context loaded: stack=python (template manifest, Python ≥3.12), 0 existing .feature files,
0 domain models (pre-build repo), 3 context docs (NAS runbook, Phase CORE scope, build plan
§FEAT-MEM-01), Graphiti configured but MCP not available this session
Phase 2: Initial Proposal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC PROPOSAL: Memory Storage Substrate (FEAT-MEM-01)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@storage-substrate
Feature: Memory Storage Substrate
  As a fleet developer
  I want memories persisted in a durable, semantically searchable store with hermetic test environments
  So that fleet knowledge survives and is recalled by meaning, and every automated gate runs without touching shared state
No Background: — the scenarios span three distinct contexts (store operations, deployment targets, test workflow) with no setup shared by all of them.

━━ GROUP A: Key Examples (12 scenarios) ━━


  # Why: Core round-trip — defines what "storing a memory" means
  @key-example @smoke
  Scenario: Storing a memory and retrieving it by its key
    Given the memory store is connected and ready
    When I store a memory with searchable content under a namespace and key
    Then retrieving that namespace and key should return the same content
    And the memory should record when it was created and last updated

  # Why: Upsert semantics — writing to an existing key must replace, never duplicate
  @key-example
  Scenario: Storing to an existing key replaces the previous memory
    Given a memory already exists under a namespace and key
    When I store new content under the same namespace and key
    Then retrieving that key should return only the new content
    And no duplicate entry should exist for that key

  # Why: Completes the memory lifecycle — deletion must remove every trace
  @key-example
  Scenario: Deleting a memory removes it from retrieval and search
    Given a stored memory that appears in semantic search results
    When I delete that memory
    Then retrieving its key should return nothing
    And it should no longer appear in any search results

  # Why: The reason pgvector exists — recall by meaning, not just by key
  @key-example @smoke
  Scenario: Semantic search returns memories ranked by relevance to the query
    Given stored memories about "database connection pooling" and "holiday rota planning"
    When I search for "how do we manage Postgres connections"
    Then the memory about database connection pooling should rank first
    And each result should include its relevance score

  # Why: Explicit acceptance criterion — similarity search combined with metadata filtering
  @key-example
  Scenario: Semantic search can be constrained by metadata filters
    Given stored memories from two different projects that are both relevant to a query
    When I search with that query filtered to one project
    Then only memories from that project should be returned
    And they should still be ranked by relevance

  # Why: Lifespan contract — the pool must follow the service lifecycle exactly (AC: opens/closes cleanly)
  @key-example @smoke
  Scenario: The connection pool lives and dies with the service
    Given the service is configured with a reachable database
    When the service starts up
    Then the store should be ready to serve operations
    When the service shuts down
    Then all database connections should be released cleanly

  # [ASSUMPTION: confidence=medium] Profiles are "mac-dev" (durable NAS target) and "test" (ephemeral target); a production profile is deferred
  # Why: One codebase, two targets — profile selection must be explicit, complete, and env-only
  @key-example
  Scenario Outline: Configuration profiles select the correct deployment target from the environment
    Given the "<profile>" environment profile is active
    When the service loads its settings
    Then the database target should be <database>
    And the embedding service target should be <embedding>

    Examples:
      | profile | database                                       | embedding                                  |
      | mac-dev | the durable shared instance over the private network | the always-on embedding service        |
      | test    | the local ephemeral instance                   | the configured test embedding              |

  # Why: The hermetic-gate promise — a throwaway instance per test run, conflict-free, gone afterwards
  @key-example @smoke
  Scenario: An ephemeral test instance provides a fresh database for a test run
    Given no test infrastructure is running
    When a test run begins
    Then a throwaway database instance should start on a port that conflicts with nothing else running
    And it should contain no memories from any previous run
    When the test run completes
    Then the instance and all its data should be gone

  # Why: The durability promise — the shared instance survives restarts with data intact (runbook gate G6)
  @key-example
  Scenario: Memories on the durable shared instance survive a restart
    Given a memory stored on the durable shared instance
    When the host restarts
    Then the instance should come back without manual intervention
    And the memory should still be retrievable and searchable

  # Why: The one sanctioned check of the real deployment — productizes runbook gates G2–G5
  @key-example
  Scenario: The documented smoke check verifies the shared instance end-to-end
    Given the durable shared instance has been deployed
    When the documented smoke check runs from the development machine
    Then it should confirm the instance is healthy
    And it should confirm vector storage capability is present
    And it should confirm the instance is reachable over the same network path the service will use
    And it should confirm data lives on the backed-up storage volume

  # Why: THE hermeticity acceptance criterion — gates must pass with the shared instance physically absent
  @key-example @smoke
  Scenario: The full test suite passes with the durable shared instance powered off
    Given the durable shared instance is powered off
    When the full automated test suite runs, including autonomous build gates
    Then every test should pass using the ephemeral instance and test embeddings
    And no connection to the durable shared instance should ever be attempted

  # Why: Unit gates need nothing but code — fake embeddings keep them network-free and fast
  @key-example @smoke
  Scenario: Unit tests pass with no database and no embedding service available
    Given no database and no embedding service are reachable
    When the unit test suite runs
    Then all unit tests should pass using fake embeddings
    And no network connection should be attempted
━━ GROUP B: Boundary Conditions (5 scenarios) ━━


  # Why: Just-at boundary — the vector schema is fixed at the model's native 768 dimensions (explicit AC)
  @boundary
  Scenario: An embedding of exactly 768 dimensions is stored and searchable
    Given the store is configured for 768-dimension embeddings
    When I store a memory whose content embeds to exactly 768 dimensions
    Then the memory should be stored successfully
    And it should be findable by semantic search

  # Why: Just-outside boundary — dimension drift (wrong model or config) must fail loudly, never truncate silently
  @boundary @negative
  Scenario Outline: An embedding with the wrong number of dimensions is rejected
    Given the store is configured for 768-dimension embeddings
    When an embedding of <dimensions> dimensions is produced for a memory
    Then storing that memory should fail
    And the error should indicate an embedding dimension mismatch

    Examples:
      | dimensions |
      | 512        |
      | 767        |
      | 769        |
      | 1024       |

  # Why: Empty-store boundary — searching nothing is a non-event, not an error
  @boundary
  Scenario: Searching an empty store returns no results without error
    Given the store contains no memories
    When I search for "anything at all"
    Then the search should succeed with no results

  # Why: Result-limit boundaries — exactly N means exactly N, ranked best-first
  @boundary
  Scenario Outline: Search returns no more results than the requested limit
    Given 15 stored memories that all relate to the search topic
    When I search with a limit of <limit>
    Then exactly <limit> results should be returned
    And they should be the <limit> most relevant matches

    Examples:
      | limit |
      | 1     |
      | 10    |
      | 15    |

  # [ASSUMPTION: confidence=medium] Unlimited searches default to at most 10 results (platform convention)
  @boundary
  Scenario: Search without an explicit limit returns at most the default number of results
    Given 15 stored memories that all relate to the search topic
    When I search without specifying a limit
    Then at most 10 results should be returned
━━ GROUP C: Negative Cases (6 scenarios) ━━


  # [ASSUMPTION: confidence=low] "Promptly" means within 10 seconds of starting
  # Why: Fail fast and loud — a half-started service against a missing database helps nobody
  @negative
  Scenario: The service refuses to start when the database is unreachable
    Given the configured database cannot be reached
    When the service starts up
    Then startup should fail promptly with a diagnostic naming the unreachable database target
    And the service should not report itself as ready

  # Why: Proves "settings via env only" — misconfiguration is caught at the door, with names, not at first use
  @negative
  Scenario: Missing required settings prevent startup with a clear message
    Given the environment provides no database connection settings
    When the service starts up
    Then startup should fail with a message naming each missing setting

  # [ASSUMPTION: confidence=medium] A write that cannot be embedded fails as a whole — no partial record remains
  # Why: Partial degradation — an embedding outage must not corrupt the store or half-write memories
  @negative
  Scenario: Storing a searchable memory fails cleanly when the embedding service is down
    Given the embedding service is unavailable
    When I store a memory that requires embedding
    Then the operation should fail with an error identifying the embedding service
    And no partial memory should be left behind
    And previously stored memories should remain retrievable by key

  # Why: The shared instance holds real fleet memory — exposure beyond LAN and tailnet is a breach (runbook firewall rule)
  @negative
  Scenario: The durable shared instance refuses connections from outside the private network
    Given the durable shared instance is running
    When a connection is attempted from outside the LAN and the private tailnet
    Then the connection should be refused
    And memories should remain inaccessible to that connection

  # [ASSUMPTION: confidence=medium] Hyphens are rejected at validation time, before reaching the database
  # Why: Explicit AC — underscores everywhere; hyphenated identifiers are FalkorDB scar tissue
  @negative
  Scenario: A namespace containing hyphens is rejected
    Given the store is connected and ready
    When I attempt to store a memory under a namespace containing hyphens
    Then the operation should be rejected
    And the error should state that identifiers must use underscores

  # Why: Marker-gating must fail honestly — an explicit integration run with no infrastructure cannot hang or half-pass
  @negative
  Scenario: An explicitly requested integration run fails clearly when no ephemeral instance can start
    Given the local container runtime is not available
    When integration tests are explicitly requested
    Then the run should fail quickly with a message explaining the missing prerequisite
━━ GROUP D: Edge Cases (6 scenarios) ━━


  # [ASSUMPTION: confidence=medium] Concurrent writes resolve to the last complete write — no merge, no corruption
  @edge-case
  Scenario: Concurrent writes to the same key leave one complete winner
    Given two writers storing different content under the same namespace and key at the same time
    When both writes complete
    Then exactly one of the two versions should be stored in full
    And no blended or partial content should ever be readable

  # [ASSUMPTION: confidence=low] Pool capacity is 10 connections; excess operations wait rather than fail
  @edge-case
  Scenario: Operations beyond pool capacity queue rather than fail
    Given the connection pool is fully occupied
    When additional store operations arrive
    Then they should wait for a free connection and then complete
    And no operation should be dropped or fail due to pool pressure

  # Why: Explicit in the build plan — parallel worktrees and AutoBuild must never share test state
  @edge-case
  Scenario: Parallel test runs each get their own isolated ephemeral instance
    Given two test runs start at the same time on the same machine
    When both runs provision their test infrastructure
    Then each should get its own instance on its own conflict-free port
    And memories written by one run should never be visible to the other

  # Why: Hermeticity includes failure — an aborted run must not poison the next one
  @edge-case
  Scenario: An aborted test run still leaves no trace behind
    Given a test run that started an ephemeral instance
    When the run is aborted before completing
    Then the ephemeral instance and its data should still be removed
    And the next test run should start completely fresh

  # Why: Resilience — a brief database outage must not require a service restart
  @edge-case
  Scenario: The service recovers after a transient database outage
    Given the service is running and the database becomes briefly unreachable
    When the database becomes reachable again
    Then subsequent store operations should succeed without restarting the service

  # Why: The backed-up volume is the durability story — a restored snapshot must yield a working store (runbook rollback path)
  @edge-case
  Scenario: Memories restored from a storage snapshot are intact and searchable
    Given a snapshot of the durable instance's storage volume exists
    When the volume is restored from that snapshot and the instance starts
    Then previously stored memories should be retrievable by key
    And semantic search over them should work as before
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: 29 scenarios across 4 groups (6 tagged @smoke)
Inferred assumptions: 10 (7 need your input; 3 resolved high-confidence from the runbook/build plan — will be confirmed in Phase 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 3: Curation — your review
For each group, reply with one of:

Action	Meaning
A — Accept	include all scenarios in this group as-is
R — Reject	exclude the whole group
M — Modify	accept with changes — give them inline (e.g. B: M — drop the 1024 example)
+ — Add	accept and add scenarios you describe
? — Defer	exclude from output, recorded as deferred

GROUP A — Key Examples (12): _
GROUP B — Boundary Conditions (5): _
GROUP C — Negative Cases (6): _
GROUP D — Edge Cases (6): _
Fast path: reply A A A A to accept all four groups. After curation I'll offer the optional edge-case expansion (Phase 4 — I have candidates around secrets never appearing in logs/diagnostics, hostile memory content stored verbatim, embedding service mid-swap latency, and disk-full on the NAS volume), then resolve the 7 open assumptions (Phase 5) before writing the files.

phase-core-build-plan.md
A A A A
Phase 3 recorded: all four groups accepted as-is (29 scenarios). Two phases of input remain — I'll batch them into this one message so you can answer both at once.

Phase 4: Edge Case Expansion (optional)
I've identified 5 additional scenarios beyond Group D — security, write-visibility, and capacity boundaries. Shown in full so you can decide directly:


  # Why: The runbook is explicit about secrets hygiene — a connection failure must never leak the credential
  @edge-case @negative
  Scenario: Database credentials never appear in logs or error messages
    Given the service is configured with a database password
    When any startup failure or store error is reported
    Then the report may name the database host and database name
    But the password should never appear in any log, error, or diagnostic output

  # Why: Memory content is data, never instructions — hostile text must round-trip inert and intact
  @edge-case
  Scenario: Hostile memory content is stored verbatim and stays inert
    Given a memory whose content contains database commands and injection-shaped text
    When I store and then retrieve that memory
    Then the retrieved content should be byte-for-byte identical to what was stored
    And no other memory or store structure should be affected

  # Why: Readers must never observe a half-written memory while a write is in flight
  @edge-case
  Scenario: A search during a concurrent write never sees a partial memory
    Given a memory is being rewritten with new content
    When a search runs while that write is in flight
    Then any result for that memory should be either the complete old version or the complete new version

  # [ASSUMPTION: confidence=low] Embedding calls are bounded at 10 seconds
  # Why: A hung embedding service must not stall store operations indefinitely
  @edge-case
  Scenario: A hung embedding service cannot stall store operations indefinitely
    Given the embedding service accepts connections but never responds
    When I store a memory that requires embedding
    Then the operation should fail within the configured time bound
    And the error should identify the embedding service as the cause

  # [ASSUMPTION: confidence=medium] When storage is full, writes fail clearly and reads continue
  # Why: The NAS volume is finite — exhaustion must degrade to reads-still-work, never corrupt
  @edge-case
  Scenario: A full storage volume fails writes clearly while reads continue
    Given the durable instance's storage volume has no free space
    When I store a new memory
    Then the write should fail with an error indicating storage is exhausted
    And existing memories should remain retrievable and searchable
[Y] include all 5 [N] skip them — or curate per-scenario inline.

Phase 5: Assumption Resolution
Need your input (7 + 2 conditional): reply with the item number and a value to override, or accept the proposal.


[1] .env.example profile set
    Proposed: "mac-dev" (NAS DSN over LAN/Tailscale + GB10 embed URL) and "test"
              (ephemeral DSN); a production/GB10 profile deferred to FEAT-MEM-04 (OD-5)
    Confidence: medium  Basis: build-plan task line says "mac-dev … and test …";
              your description said "mac-dev-vs-nas" — naming differs

[2] Default search result limit (when caller gives none)
    Proposed: 10  Confidence: medium  Basis: LangGraph store convention

[3] Concurrent same-key writes
    Proposed: last complete write wins; no merge, no partials
    Confidence: medium  Basis: Postgres upsert semantics

[4] Connection pool capacity
    Proposed: max 10 connections; operations beyond capacity queue (wait), never fail
    Confidence: low  Basis: not stated anywhere; common asyncpg/psycopg-pool sizing

[5] Write atomicity when embedding fails
    Proposed: the whole write fails; no partial record
    Confidence: medium  Basis: AsyncPostgresStore behaviour; matches two-layer idempotency intent

[6] Startup fail-fast bound (DB unreachable)
    Proposed: fails within 10 seconds with diagnostic
    Confidence: low  Basis: nothing documented; typical connect-timeout practice

[7] Hyphen rejection point
    Proposed: rejected at validation time, before reaching the database
    Confidence: medium  Basis: "underscores everywhere" constraint is explicit; WHERE to enforce is not

[8] (only if Phase 4 = Y) Embedding call timeout
    Proposed: 10 seconds  Confidence: low

[9] (only if Phase 4 = Y) Full-volume behaviour
    Proposed: writes fail with clear error; reads/search continue  Confidence: medium
Resolved high-confidence (no action needed — recorded in the manifest):

Integration marker is integration, excluded from the default run — template convention
The NAS smoke is deploy/nas/smoke.sh productizing runbook gates G2–G5, run manually from the Mac
Integration tests use real nomic embeddings over Tailscale (build-plan AC); fake embeddings are for unit tests only
Search-during-write sees only committed state — Postgres transactional guarantee (backs the Phase 4 concurrency scenario)
Fast path: reply Y, accept all — includes the 5 edge cases and all proposed defaults. Then I write the three output files to features/storage-substrate/ and run the Gherkin normalization check.

accept all
All assumptions accepted at proposed values and the 5 expansion scenarios are in — final set: 34 scenarios, 13 assumptions. Moving to Phase 6: Output Generation.

Bash Get UTC timestamp and probe Gherkin validation tooling
IN
date -u +%Y-%m-%dT%H:%M:%SZ; command -v uv python3; python3 -c "import gherkin; print('gherkin-official available')" 2>&1 | tail -1

OUT
2026-06-12T15:19:41Z
/opt/homebrew/bin/uv
/usr/local/bin/python3
gherkin-official available
Timestamp captured and the official gherkin parser is available for validation. Writing the three output files:

Write storage-substrate.feature
329 lines
# Generated by /feature-spec
# Feature: Memory Storage Substrate (FEAT-MEM-01)
# Stack: python
# Assumptions: 13 (see storage-substrate_assumptions.yaml)
# Generated: 2026-06-12T15:19:41Z
#
# Context sources: docs/research/ideas/phase-core-build-plan.md (FEAT-MEM-01),
# docs/research/ideas/phase-core-scope.md, docs/runbooks/RUNBOOK-nas-postgres-deploy.md
#
# No Background block: the scenarios span three contexts (store operations,
# deployment targets, test workflow) with no setup step shared by all of them.

@storage-substrate
Feature: Memory Storage Substrate
  As a fleet developer
  I want memories persisted in a durable, semantically searchable store with hermetic test environments
  So that fleet knowledge survives and is recalled by meaning, and every automated gate runs without touching shared state

  # ───────────────────────── Store semantics ─────────────────────────

  # Why: Core round-trip — defines what "storing a memory" means
  @key-example @smoke
  Scenario: Storing a memory and retrieving it by its key
    Given the memory store is connected and ready
    When I store a memory with searchable content under a namespace and key
    Then retrieving that namespace and key should return the same content
    And the memory should record when it was created and last updated

  # Why: Upsert semantics — writing to an existing key must replace, never duplicate
  @key-example
  Scenario: Storing to an existing key replaces the previous memory
    Given a memory already exists under a namespace and key
    When I store new content under the same namespace and key
    Then retrieving that key should return only the new content
    And no duplicate entry should exist for that key

  # Why: Completes the memory lifecycle — deletion must remove every trace
  @key-example
  Scenario: Deleting a memory removes it from retrieval and search
    Given a stored memory that appears in semantic search results
    When I delete that memory
    Then retrieving its key should return nothing
    And it should no longer appear in any search results

  # Why: The reason pgvector exists — recall by meaning, not just by key
  @key-example @smoke
  Scenario: Semantic search returns memories ranked by relevance to the query
    Given stored memories about "database connection pooling" and "holiday rota planning"
    When I search for "how do we manage Postgres connections"
    Then the memory about database connection pooling should rank first
    And each result should include its relevance score

  # Why: Explicit acceptance criterion — similarity search combined with metadata filtering
  @key-example
  Scenario: Semantic search can be constrained by metadata filters
    Given stored memories from two different projects that are both relevant to a query
    When I search with that query filtered to one project
    Then only memories from that project should be returned
    And they should still be ranked by relevance

  # ──────────────────── Lifespan and configuration ───────────────────

  # Why: Lifespan contract — the pool must follow the service lifecycle exactly
  @key-example @smoke
  Scenario: The connection pool lives and dies with the service
    Given the service is configured with a reachable database
    When the service starts up
    Then the store should be ready to serve operations
    When the service shuts down
    Then all database connections should be released cleanly

  # Why: One codebase, two targets — profile selection must be explicit, complete, and env-only
  # [ASSUMPTION: confidence=medium] Profiles are "mac-dev" (durable NAS target) and "test" (ephemeral target); a production profile is deferred to FEAT-MEM-04 (OD-5)
  @key-example
  Scenario Outline: Configuration profiles select the correct deployment target from the environment
    Given the "<profile>" environment profile is active
    When the service loads its settings
    Then the database target should be <database>
    And the embedding service target should be <embedding>

    Examples:
      | profile | database                                             | embedding                       |
      | mac-dev | the durable shared instance over the private network | the always-on embedding service |
      | test    | the local ephemeral instance                         | the configured test embedding   |

  # ──────────────── Deployment targets and test workflow ─────────────

  # Why: The hermetic-gate promise — a throwaway instance per test run, conflict-free, gone afterwards
  @key-example @smoke
  Scenario: An ephemeral test instance provides a fresh database for a test run
    Given no test infrastructure is running
    When a test run begins
    Then a throwaway database instance should start on a port that conflicts with nothing else running
    And it should contain no memories from any previous run
    When the test run completes
    Then the instance and all its data should be gone

  # Why: The durability promise — the shared instance survives restarts with data intact (runbook gate G6)
  @key-example
  Scenario: Memories on the durable shared instance survive a restart
    Given a memory stored on the durable shared instance
    When the host restarts
    Then the instance should come back without manual intervention
    And the memory should still be retrievable and searchable

  # Why: The one sanctioned check of the real deployment — productizes runbook gates G2 to G5
  @key-example
  Scenario: The documented smoke check verifies the shared instance end-to-end
    Given the durable shared instance has been deployed
    When the documented smoke check runs from the development machine
    Then it should confirm the instance is healthy
    And it should confirm vector storage capability is present
    And it should confirm the instance is reachable over the same network path the service will use
    And it should confirm data lives on the backed-up storage volume

  # Why: THE hermeticity acceptance criterion — gates must pass with the shared instance physically absent
  @key-example @smoke
  Scenario: The full test suite passes with the durable shared instance powered off
    Given the durable shared instance is powered off
    When the full automated test suite runs, including autonomous build gates
    Then every test should pass using the ephemeral instance and test embeddings
    And no connection to the durable shared instance should ever be attempted

  # Why: Unit gates need nothing but code — fake embeddings keep them network-free and fast
  @key-example @smoke
  Scenario: Unit tests pass with no database and no embedding service available
    Given no database and no embedding service are reachable
    When the unit test suite runs
    Then all unit tests should pass using fake embeddings
    And no network connection should be attempted

  # ───────────────────── Boundary conditions ─────────────────────────

  # Why: Just-at boundary — the vector schema is fixed at the model's native 768 dimensions
  @boundary
  Scenario: An embedding of exactly 768 dimensions is stored and searchable
    Given the store is configured for 768-dimension embeddings
    When I store a memory whose content embeds to exactly 768 dimensions
    Then the memory should be stored successfully
    And it should be findable by semantic search

  # Why: Just-outside boundary — dimension drift (wrong model or config) must fail loudly, never truncate silently
  @boundary @negative
  Scenario Outline: An embedding with the wrong number of dimensions is rejected
    Given the store is configured for 768-dimension embeddings
    When an embedding of <dimensions> dimensions is produced for a memory
    Then storing that memory should fail
    And the error should indicate an embedding dimension mismatch

    Examples:
      | dimensions |
      | 512        |
      | 767        |
      | 769        |
      | 1024       |

  # Why: Empty-store boundary — searching nothing is a non-event, not an error
  @boundary
  Scenario: Searching an empty store returns no results without error
    Given the store contains no memories
    When I search for "anything at all"
    Then the search should succeed with no results

  # Why: Result-limit boundaries — exactly N means exactly N, ranked best-first
  @boundary
  Scenario Outline: Search returns no more results than the requested limit
    Given 15 stored memories that all relate to the search topic
    When I search with a limit of <limit>
    Then exactly <limit> results should be returned
    And they should be the <limit> most relevant matches

    Examples:
      | limit |
      | 1     |
      | 10    |
      | 15    |

  # [ASSUMPTION: confidence=medium] Unlimited searches default to at most 10 results (platform convention)
  @boundary
  Scenario: Search without an explicit limit returns at most the default number of results
    Given 15 stored memories that all relate to the search topic
    When I search without specifying a limit
    Then at most 10 results should be returned

  # ─────────────────────── Negative cases ────────────────────────────

  # Why: Fail fast and loud — a half-started service against a missing database helps nobody
  # [ASSUMPTION: confidence=low] "Promptly" means within 10 seconds of starting
  @negative
  Scenario: The service refuses to start when the database is unreachable
    Given the configured database cannot be reached
    When the service starts up
    Then startup should fail promptly with a diagnostic naming the unreachable database target
    And the service should not report itself as ready

  # Why: Proves "settings via env only" — misconfiguration is caught at the door, with names, not at first use
  @negative
  Scenario: Missing required settings prevent startup with a clear message
    Given the environment provides no database connection settings
    When the service starts up
    Then startup should fail with a message naming each missing setting

  # Why: Partial degradation — an embedding outage must not corrupt the store or half-write memories
  # [ASSUMPTION: confidence=medium] A write that cannot be embedded fails as a whole — no partial record remains
  @negative
  Scenario: Storing a searchable memory fails cleanly when the embedding service is down
    Given the embedding service is unavailable
    When I store a memory that requires embedding
    Then the operation should fail with an error identifying the embedding service
    And no partial memory should be left behind
    And previously stored memories should remain retrievable by key

  # Why: The shared instance holds real fleet memory — exposure beyond LAN and tailnet is a breach
  @negative
  Scenario: The durable shared instance refuses connections from outside the private network
    Given the durable shared instance is running
    When a connection is attempted from outside the LAN and the private tailnet
    Then the connection should be refused
    And memories should remain inaccessible to that connection

  # Why: Explicit constraint — underscores everywhere; hyphenated identifiers are FalkorDB scar tissue
  # [ASSUMPTION: confidence=medium] Hyphens are rejected at validation time, before reaching the database
  @negative
  Scenario: A namespace containing hyphens is rejected
    Given the store is connected and ready
    When I attempt to store a memory under a namespace containing hyphens
    Then the operation should be rejected
    And the error should state that identifiers must use underscores

  # Why: Marker-gating must fail honestly — an explicit integration run with no infrastructure cannot hang or half-pass
  @negative
  Scenario: An explicitly requested integration run fails clearly when no ephemeral instance can start
    Given the local container runtime is not available
    When integration tests are explicitly requested
    Then the run should fail quickly with a message explaining the missing prerequisite

  # ──────────────────────── Edge cases ───────────────────────────────

  # Why: Concurrent writers must converge on one readable truth
  # [ASSUMPTION: confidence=medium] Concurrent writes resolve to the last complete write — no merge, no corruption
  @edge-case
  Scenario: Concurrent writes to the same key leave one complete winner
    Given two writers storing different content under the same namespace and key at the same time
    When both writes complete
    Then exactly one of the two versions should be stored in full
    And no blended or partial content should ever be readable

  # Why: Load beyond pool capacity must degrade to waiting, never to dropped operations
  # [ASSUMPTION: confidence=low] Pool capacity is 10 connections; excess operations wait rather than fail
  @edge-case
  Scenario: Operations beyond pool capacity queue rather than fail
    Given the connection pool is fully occupied
    When additional store operations arrive
    Then they should wait for a free connection and then complete
    And no operation should be dropped or fail due to pool pressure

  # Why: Explicit in the build plan — parallel worktrees and AutoBuild must never share test state
  @edge-case
  Scenario: Parallel test runs each get their own isolated ephemeral instance
    Given two test runs start at the same time on the same machine
    When both runs provision their test infrastructure
    Then each should get its own instance on its own conflict-free port
    And memories written by one run should never be visible to the other

  # Why: Hermeticity includes failure — an aborted run must not poison the next one
  @edge-case
  Scenario: An aborted test run still leaves no trace behind
    Given a test run that started an ephemeral instance
    When the run is aborted before completing
    Then the ephemeral instance and its data should still be removed
    And the next test run should start completely fresh

  # Why: Resilience — a brief database outage must not require a service restart
  @edge-case
  Scenario: The service recovers after a transient database outage
    Given the service is running and the database becomes briefly unreachable
    When the database becomes reachable again
    Then subsequent store operations should succeed without restarting the service

  # Why: The backed-up volume is the durability story — a restored snapshot must yield a working store
  @edge-case
  Scenario: Memories restored from a storage snapshot are intact and searchable
    Given a snapshot of the durable instance's storage volume exists
    When the volume is restored from that snapshot and the instance starts
    Then previously stored memories should be retrievable by key
    And semantic search over them should work as before

  # Why: The runbook is explicit about secrets hygiene — a connection failure must never leak the credential
  @edge-case @negative
  Scenario: Database credentials never appear in logs or error messages
    Given the service is configured with a database password
    When any startup failure or store error is reported
    Then the report may name the database host and database name
    But the password should never appear in any log, error, or diagnostic output

  # Why: Memory content is data, never instructions — hostile text must round-trip inert and intact
  @edge-case
  Scenario: Hostile memory content is stored verbatim and stays inert
    Given a memory whose content contains database commands and injection-shaped text
    When I store and then retrieve that memory
    Then the retrieved content should be byte-for-byte identical to what was stored
    And no other memory or store structure should be affected

  # Why: Readers must never observe a half-written memory while a write is in flight
  # [ASSUMPTION: confidence=high] Reads see only committed state — old or new in full, guaranteed by the database
  @edge-case
  Scenario: A search during a concurrent write never sees a partial memory
    Given a memory is being rewritten with new content
    When a search runs while that write is in flight
    Then any result for that memory should be either the complete old version or the complete new version

  # Why: A hung embedding service must not stall store operations indefinitely
  # [ASSUMPTION: confidence=low] Embedding calls are bounded at 10 seconds
  @edge-case
  Scenario: A hung embedding service cannot stall store operations indefinitely
    Given the embedding service accepts connections but never responds
    When I store a memory that requires embedding
    Then the operation should fail within the configured time bound
    And the error should identify the embedding service as the cause

  # Why: The NAS volume is finite — exhaustion must degrade to reads-still-work, never corrupt
  # [ASSUMPTION: confidence=medium] When storage is full, writes fail clearly and reads continue
  @edge-case
  Scenario: A full storage volume fails writes clearly while reads continue
    Given the durable instance's storage volume has no free space
    When I store a new memory
    Then the write should fail with an error indicating storage is exhausted
    And existing memories should remain retrievable and searchable
Write storage-substrate_assumptions.yaml
100 lines
# Assumptions manifest for storage-substrate.feature
# Generated by /feature-spec

feature: "Memory Storage Substrate"
generated: "2026-06-12T15:19:41Z"
stack: "python"
review_required: true

assumptions:
  - id: "ASSUM-001"
    scenario: "Configuration profiles select the correct deployment target from the environment"
    assumption: "Profiles in .env.example are 'mac-dev' (NAS DSN over LAN/Tailscale + GB10 embed URL) and 'test' (ephemeral DSN); a production/GB10 profile is deferred to FEAT-MEM-04 (OD-5)"
    confidence: medium
    basis: "Build-plan FEAT-MEM-01 task line names mac-dev and test profiles; the feature description said 'mac-dev-vs-nas', so naming differs between sources"
    human_response: "confirmed"

  - id: "ASSUM-002"
    scenario: "Search without an explicit limit returns at most the default number of results"
    assumption: "Default search result limit is 10 when the caller specifies none"
    confidence: medium
    basis: "LangGraph store search convention; not stated in the description or docs"
    human_response: "confirmed"

  - id: "ASSUM-003"
    scenario: "Concurrent writes to the same key leave one complete winner"
    assumption: "Concurrent writes to the same key resolve to the last complete write; no merge, no partial state"
    confidence: medium
    basis: "Postgres upsert semantics; consistent with the two-layer idempotency constraint"
    human_response: "confirmed"

  - id: "ASSUM-004"
    scenario: "Operations beyond pool capacity queue rather than fail"
    assumption: "Connection pool capacity is 10 connections; operations beyond capacity wait for a free connection rather than fail"
    confidence: low
    basis: "Not stated anywhere; common asyncpg/psycopg-pool sizing practice — verify during implementation"
    human_response: "confirmed"

  - id: "ASSUM-005"
    scenario: "Storing a searchable memory fails cleanly when the embedding service is down"
    assumption: "A write that cannot be embedded fails as a whole; no partial record remains"
    confidence: medium
    basis: "AsyncPostgresStore behaviour; matches the two-layer idempotency intent"
    human_response: "confirmed"

  - id: "ASSUM-006"
    scenario: "The service refuses to start when the database is unreachable"
    assumption: "Startup failure surfaces within 10 seconds when the database is unreachable"
    confidence: low
    basis: "Nothing documented; typical connect-timeout practice — verify during implementation"
    human_response: "confirmed"

  - id: "ASSUM-007"
    scenario: "A namespace containing hyphens is rejected"
    assumption: "Hyphenated namespace components are rejected at validation time, before reaching the database"
    confidence: medium
    basis: "'Underscores everywhere' constraint is explicit in the scope doc; the enforcement point is not"
    human_response: "confirmed"

  - id: "ASSUM-008"
    scenario: "A hung embedding service cannot stall store operations indefinitely"
    assumption: "Embedding calls are bounded at 10 seconds"
    confidence: low
    basis: "No timeout documented; proposed as a sane default for a LAN/Tailscale embedding endpoint — verify during implementation"
    human_response: "confirmed"

  - id: "ASSUM-009"
    scenario: "A full storage volume fails writes clearly while reads continue"
    assumption: "When the storage volume is full, writes fail with a clear error and existing memories remain readable and searchable"
    confidence: medium
    basis: "Standard Postgres disk-exhaustion behaviour; matches ADR-SP-007's re-indexable corpus posture"
    human_response: "confirmed"

  - id: "ASSUM-010"
    scenario: "An explicitly requested integration run fails clearly when no ephemeral instance can start"
    assumption: "Integration tests are gated by the 'integration' pytest marker and excluded from the default test run"
    confidence: high
    basis: "nats-asyncio-service template convention (@pytest.mark.integration exclusion) and build-plan 'marker-gated integration tests'"
    human_response: "confirmed"

  - id: "ASSUM-011"
    scenario: "The documented smoke check verifies the shared instance end-to-end"
    assumption: "The documented NAS smoke is deploy/nas/smoke.sh productizing runbook gates G2-G5, run manually from the Mac"
    confidence: high
    basis: "RUNBOOK-nas-postgres-deploy.md footer and build-plan FEAT-MEM-01 task list"
    human_response: "confirmed"

  - id: "ASSUM-012"
    scenario: "The full test suite passes with the durable shared instance powered off"
    assumption: "Integration tests use real nomic embeddings over Tailscale (GB10 llama-swap :9000); fake embeddings are for unit tests only"
    confidence: high
    basis: "Build-plan acceptance criterion: round-trip with real nomic embeddings against the ephemeral instance; hermeticity excludes the NAS, not GB10"
    human_response: "confirmed"

  - id: "ASSUM-013"
    scenario: "A search during a concurrent write never sees a partial memory"
    assumption: "Reads observe only committed state — the complete old or complete new version, never a partial"
    confidence: high
    basis: "Postgres transactional (MVCC) guarantee"
    human_response: "confirmed"
Write storage-substrate_summary.md
46 lines
# Feature Spec Summary: Memory Storage Substrate

**Feature**: FEAT-MEM-01 (Phase CORE build plan)
**Stack**: python
**Generated**: 2026-06-12T15:19:41Z
**Scenarios**: 34 total (6 smoke, 0 regression; 3 scenario outlines covering 9 example rows)
**Assumptions**: 13 total (4 high / 6 medium / 3 low confidence)
**Review required**: Yes — 3 low-confidence values were human-confirmed as placeholders at spec time; verify during planning/implementation

## Scope

The storage substrate for fleet-memory: LangGraph `AsyncPostgresStore` on Postgres 16 + pgvector, with a 768-dimension nomic-embed-text-v1.5 embed function served by llama-swap on GB10 (:9000). Two deployment targets — `deploy/local/` provides an ephemeral, random-port, throwaway instance used by ALL automated test gates (including AutoBuild), and `deploy/nas/` provides the durable shared instance on the Synology NAS (backed-up volume, port 5432 exposed to LAN/Tailscale only). The specification covers store semantics (put/get/delete/semantic search with metadata filters), the lifespan-managed connection pool, pydantic-settings profile configuration, and the three-tier test strategy (fake-embed unit tests, marker-gated integration tests against the ephemeral instance, one documented smoke against the NAS productizing runbook gates G2–G5).

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 12 |
| Boundary conditions (@boundary) | 5 |
| Negative cases (@negative, primary) | 6 |
| Edge cases (@edge-case) | 11 |

`@negative` additionally appears on 2 scenarios whose primary category is boundary/edge (dimension mismatch, credential hygiene). `@smoke` marks the 6-scenario minimal set: key round-trip, ranked search, lifespan pool, ephemeral instance lifecycle, NAS-off hermeticity, zero-network unit gates.

## Deferred Items

None — all four proposal groups and all five expansion scenarios were accepted.

A production/GB10 runtime profile for configuration was intentionally **not specified** here; it is deferred to FEAT-MEM-04 per build-plan open decision OD-5 (recorded in ASSUM-001).

## Open Assumptions (low confidence)

These were accepted as placeholders by the human during spec review and need verification during `/feature-plan` or implementation:

- **ASSUM-004** — Connection pool capacity is 10; operations beyond capacity queue rather than fail
- **ASSUM-006** — Startup fail-fast surfaces within 10 seconds when the database is unreachable
- **ASSUM-008** — Embedding calls are bounded at 10 seconds

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md

The build plan's prefilled command (`/feature-plan FEAT-XXXX`) applies once a GuardKit feature id is assigned. Feature-plan Step 11 will link these scenarios to tasks via `@task:<TASK-ID>` tags — do not hand-tag ahead of that.
All three files written. Now the mandatory normalization/validation step — trying the GuardKit normalizer first, falling back to the official gherkin parser it wraps:

Bash Run GuardKit feature-spec normalizer on the new .feature file
IN
python3 -m installer.core.commands.lib.feature_spec_normalize features/storage-substrate/storage-substrate.feature 2>&1; echo "normalizer exit: $?"

OUT
already clean: features/storage-substrate/storage-substrate.feature
normalizer exit: 0
Edit phase-core-build-plan.md
Modified
Edit phase-core-build-plan.md
Added 2 lines
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Memory Storage Substrate (FEAT-MEM-01)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:

storage-substrate.feature — validated clean by the Gherkin normalizer (exit 0, parser-safe for /feature-plan Step 11)
storage-substrate_assumptions.yaml
storage-substrate_summary.md
Scenarios: 34 total (3 outlines covering 9 example rows)

@key-example: 12	@boundary: 5	@negative: 6 (+2 cross-tagged)	@edge-case: 11
@smoke: 6	@regression: 0		
Assumptions: 13 total — high: 4 (auto-proceed) · medium: 6 (Coach review) · low: 3 (flagged)

REVIEW REQUIRED: 3 low-confidence values you accepted as placeholders — pool capacity 10 (ASSUM-004), 10s startup fail-fast (ASSUM-006), 10s embedding timeout (ASSUM-008). They're recorded in the manifest for verification during planning/implementation.

Deferred: none. The production/GB10 config profile was deliberately left out per OD-5 (deferred to FEAT-MEM-04) and recorded in ASSUM-001.

Also done per the build plan's own convention: phase-core-build-plan.md now shows FEAT-MEM-01 as Spec'd with a Status line pointing at features/storage-substrate/ (marked "commit pending" since nothing is committed — say the word if you want these committed and I'll add the hash to the Status line).

Next step:


/feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md
please update the build plan with the current status and update the /feature-plan command listed
Two edits to phase-core-build-plan.md: refresh the FEAT-MEM-01 Status line, and replace the placeholder /feature-plan FEAT-XXXX with the ready-to-run command (keeping the executed /feature-spec invocation as a comment for the record, since docs/ isn't committed yet and the long description exists nowhere else):

Edit phase-core-build-plan.md
Modified
Edit phase-core-build-plan.md
Added 1 line
Build plan updated. The FEAT-MEM-01 section now reflects the current state:

Status line — records that /feature-spec was executed on 2026-06-12, points at features/storage-substrate/ (34 scenarios, 13 assumptions), names the three low-confidence placeholders to verify at plan/build time (pool capacity, startup fail-fast bound, embed timeout), notes the spec commit is pending, and says the next action is the /feature-plan command below it.
Spec & Plan Commands block — the executed /feature-spec invocation is preserved as a # DONE 2026-06-12 comment (it's not in git history yet, so the original description text stays recoverable), and the placeholder /feature-plan FEAT-XXXX is replaced with the ready-to-run command:

/feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md
The Feature Summary row was already flipped to Spec'd (GuardKit id stays — until /feature-plan assigns one, per the plan-update convention). When you commit the spec, the Status line's "spec commit pending" is the one phrase to swap for the hash.