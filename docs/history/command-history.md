
/feature-spec "Storage substrate: LangGraph AsyncPostgresStore on Postgres 16 + pgvector with nomic-embed-text-v1.5 768-dim embed function via llama-swap :9000; dual deploy targets — deploy/local ephemeral compose for hermetic Mac test gates (random-port, throwaway, used by ALL automated tests incl. AutoBuild) and deploy/nas Synology Container Manager compose for the durable shared instance (backed-up volume, LAN/Tailscale-only 5432); lifespan-managed pool; pydantic-settings DSN/embed config with .env.example profiles for mac-dev-vs-nas; fake-embed unit tests + marker-gated integration tests against the ephemeral instance + one documented smoke against the NAS instance"


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



/feature-plan "Memory Storage Substrate" --context features/storage-substrate/storage-substrate_summary.md


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




/feature-spec "Typed payload registry: Pydantic models for ADR, review report, build outcome, pattern, warning, seed module, generic document; natural-key + declared-supersession + domain-tags conventions; payload_type dispatch registry; exhaustive validation tests"


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Typed Payload Registry (FEAT-MEM-02)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/typed-payload-registry/typed-payload-registry.feature
  features/typed-payload-registry/typed-payload-registry_assumptions.yaml
  features/typed-payload-registry/typed-payload-registry_summary.md

Scenarios: 29 total (validated by official gherkin parser)
  @key-example: 7    @boundary: 5
  @negative: 8       @edge-case: 14
  @smoke: 8          @regression: 5

Assumptions: 11 total
  high: 4   (auto-proceed)
  medium: 3 (Coach review recommended)
  low: 4    (human review required)

REVIEW REQUIRED: 4 low-confidence assumptions need verification
  ASSUM-005 (domain_tags format)
  ASSUM-006 (version stamp = monotonic int from 1)
  ASSUM-007 (source_ref required provenance string)
  ASSUM-011 (self-supersession rejected / cross-project allowed)
  See: features/typed-payload-registry/typed-payload-registry_assumptions.yaml

Deferred: 0 groups. related_keys excluded (ASSUM-008), deferred to retrieval/writer.

Next steps:
  Review: features/typed-payload-registry/typed-payload-registry.feature
  Pass to feature-plan:
    /feature-plan "Typed Payload Registry" \
      --context features/typed-payload-registry/typed-payload-registry_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The spec maps cleanly onto the four FEAT-MEM-02 acceptance criteria in the build plan: hyphen rejection (Group C), natural-key stability (@regression property scenario), registry round-trip (Group A), and natural-key-shaped supersedes validation (Group B/C). The four low-confidence assumptions are the items worth confirming before /feature-plan — particularly the version stamp semantics, since FEAT-MEM-03's upsert/versioning behaviour depends on it.







/feature-plan "Typed Payload Registry" \
      --context features/typed-payload-registry/typed-payload-registry_summary.md



━━━ FEATURE PLANNING COMPLETE: Typed Payload Registry ━━━
Approach: Option 1 — shared BasePayload + 7 subclasses + registration-time dispatch registry
Decisions: Context A → focus=all, trade-off=balanced · Context B → approach=Option 1, testing=BDD-driven

Created: tasks/backlog/typed-payload-registry/

├── README.md
├── IMPLEMENTATION-GUIDE.md   (Data-flow + Integration-contract + Dependency diagrams + §4 contracts)
├── TASK-TPR-001-payload-base-conventions.md   (declarative, cx6, wave 1)
├── TASK-TPR-002-seven-payload-types.md        (declarative, cx4, wave 2)
├── TASK-TPR-003-dispatch-registry.md          (feature,     cx5, wave 3)  + Seam Tests
└── TASK-TPR-004-bdd-scenario-suite.md         (testing,     cx4, wave 4)
Feature YAML: .guardkit/features/FEAT-MEM-02.yaml — ✅ validates
Review task: TASK-REV-C42F (still in backlog; /task-complete TASK-REV-C42F to archive)
AC-quality review: 0 unverifiable acceptance criteria (warn-mode)
Execution: sequential chain (4 waves, one task each)
001 base → 002 types → 003 registry → 004 BDD suite. Parallelism was considered and rejected — each layer depends on the previous; the base task carries the design risk and is isolated for thorough review.

BDD linking (Step 11): R2 oracle activated
All 29 scenarios tagged @task: → 16 to TASK-TPR-001 (validation/key behaviour), 2 to TASK-TPR-002 (concrete-type fields), 11 to TASK-TPR-003 (registry/round-trip). Every scenario cleared the 0.6 confidence threshold, so each task's /task-work will run its own scenarios as a Phase-4 oracle.

Disconnection check
The only dotted read paths in the data-flow diagram are the downstream writer (FEAT-MEM-03) and relay (FEAT-MEM-04) — out of scope here by design; this feature provides the seam they consume. No in-scope write path lacks a read. Acknowledged in the guide, not a defect.

⚠️ One open item for you — R3 smoke gates (optional)
The generator nudged that FEAT-MEM-02 has 4 waves but no smoke_gates: block. For this feature I deliberately left it unset: the waves are single tasks in a strict chain, the final wave is the full BDD suite, and per-task Coach validation already runs pytest -k payload. There's no meaningful mid-chain composition to smoke-test. If you'd still like a between-wave gate (e.g. run tests/unit after wave 3), say so and I'll add a schema-valid block.

Next steps

/task-work TASK-TPR-001          # implement sequentially, or…
/feature-build FEAT-MEM-02       # autonomous AutoBuild
Want me to mark the review task TASK-REV-C42F complete, or leave it in backlog?






/feature-spec "Deterministic writer service: typed payload to AsyncPostgresStore records with UUIDv5 natural-key idempotency, content-hash upsert semantics, declared supersession linking, embed-on-write, per-project namespaces; zero LLM calls by construction; idempotency and supersession test suites"




━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Deterministic Writer (FEAT-MEM-03)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/deterministic-writer/deterministic-writer.feature
  features/deterministic-writer/deterministic-writer_assumptions.yaml
  features/deterministic-writer/deterministic-writer_summary.md

Scenarios: 29 total  (validated: parses cleanly under pytest-bdd)
  @key-example: 8    @boundary: 4
  @negative: 9       @edge-case: 15
  @smoke: 13         @regression: 4

Assumptions: 10 total
  high: 3   (auto-proceed)
  medium: 5 (Coach review recommended)
  low: 2    (human review required)

REVIEW REQUIRED: 2 low-confidence assumptions need verification
  ASSUM-008 — forward supersession (supersede a not-yet-written key)
  ASSUM-010 — batch write behaviour / partial-batch failure mode
  See: features/deterministic-writer/deterministic-writer_assumptions.yaml

Deferred: 0 groups

Next steps:
  Review: features/deterministic-writer/deterministic-writer.feature
  Pass to feature-plan:
    /feature-plan "Deterministic Writer" \
      --context features/deterministic-writer/deterministic-writer_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Note on the normalization backstop: the documented installer.core.commands.lib.feature_spec_normalize module isn't vendored into this repo (it ships with the GuardKit installer, not the fleet-memory project), so I validated equivalently by parsing the file with the project's own pytest-bdd grammar — the same official Gherkin engine /feature-plan Step 11 relies on. It accepted all 29 scenarios with no wrapped step lines, so the spec is safe to hand to /feature-plan.

The two low-confidence assumptions (forward supersession, batch failure mode) are genuine design decisions the build plan doesn't pin down — worth settling before or during /feature-plan rather than letting the writer implementation make the call silently.





/feature-plan "Deterministic Writer" \
      --context features/deterministic-writer/deterministic-writer_summary.md


Feature planning complete — FEAT-MEM-03 Deterministic Writer

✅ Feature FEAT-MEM-03 created  ·  5 tasks  ·  AC-quality: 0 unverifiable
What was generated:

Artifact	Path
Feature file	.guardkit/features/FEAT-MEM-03.yaml (+ verified smoke_gates)
Tasks + guide	tasks/backlog/deterministic-writer/ (README, IMPLEMENTATION-GUIDE, 5 task files)
Review report	.claude/reviews/TASK-REV-DW03-review-report.md
BDD spec	deterministic-writer.feature — all 29 scenarios @task:-tagged
Tasks & waves (auto-detected):


Wave 1: TASK-DW-001  identity + content-hash helpers           (feature, c4)
Wave 2: TASK-DW-002  writer core / idempotent upsert            (feature, c7)
Wave 3: TASK-DW-003  supersession linking          ‖  TASK-DW-004  idempotency + zero-LLM tests
        (feature, c6)                                 (testing, c4)
   ── smoke gate: pytest tests/unit -x ──
Wave 4: TASK-DW-005  supersession tests                         (testing, c4)
Diagrams (in IMPLEMENTATION-GUIDE.md): data-flow read/write paths (no disconnections), integration-contract sequence (proves the only external model is the embedder, not an LLM), and the task-dependency graph. §4 contracts documented: writer→store record value (content field drives embed-on-write), UUIDv5 identity, supersession link, and the FEAT-MEM-02 payload input.

Validations passed: Feature FEAT-MEM-03 is valid (pre-flight) · smoke_gates.command paths OK.

⚠️ One prerequisite before /feature-build: FEAT-MEM-02 (typed payload registry) is still in_progress in a worktree and not yet on main. The writer imports fleet_memory.payloads, so merge FEAT-MEM-02 first, then:


/feature-build FEAT-MEM-03
The two REVIEW-REQUIRED assumptions (ASSUM-008 forward supersession, ASSUM-010 batch one-per-key) were already confirmed in the spec, so they're baked into TASK-DW-003 and TASK-DW-002 acceptance criteria rather than left open.








/feature-spec "Relay integration: FastStream durable consumer on MEMORY stream consuming MemoryEpisodeV1 from nats-core; structured_json episodes dispatch through payload registry to deterministic writer; markdown/text episodes chunk+embed with heading-aware chunking; ack/nak/DLQ per relay scope; TestNatsBroker test suite incl. poison message and redelivery idempotency"




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








/feature-spec "Relay integration: FastStream durable consumer on MEMORY stream consuming MemoryEpisodeV1 from nats-core; structured_json episodes dispatch through payload registry to deterministic writer; markdown/text episodes chunk+embed with heading-aware chunking; ack/nak/DLQ per relay scope; TestNatsBroker test suite incl. poison message and redelivery idempotency"




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







/feature-spec "Retrieval API: search with project/payload-type/domain-tag filters + vector query + token budget, default supersession exclusion, ranked composition porting guardkit job-specific context semantics, coverage scoring; probe-set evaluation harness for the 15-query retrieval-parity gate"



━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Retrieval API + Context Assembly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/retrieval-api/retrieval-api.feature
  features/retrieval-api/retrieval-api_assumptions.yaml
  features/retrieval-api/retrieval-api_summary.md

Scenarios: 31 total
  @key-example: 8    @boundary: 6
  @negative: 11      @edge-case: 12
  @smoke: 10         @regression: 6

Assumptions: 9 total
  high: 3 (auto-proceed)
  medium: 2 (Coach review recommended)
  low: 4 (human review required)

REVIEW REQUIRED: 4 low-confidence assumptions need verification
  ASSUM-001 (complexity bands), ASSUM-007 (parity pass condition),
  ASSUM-008 (empty-request handling), ASSUM-009 (over-budget memory)
  See: features/retrieval-api/retrieval-api_assumptions.yaml

Deferred: 0 scenario groups

Next steps:
  Review: features/retrieval-api/retrieval-api.feature
  Pass to feature-plan: /feature-plan "Retrieval API + Context Assembly" \
    --context features/retrieval-api/retrieval-api_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The spec is written and parser-validated. Two things worth your attention before /feature-plan:

ASSUM-001 (complexity bands) is the load-bearing unknown — the guardkit job-specific context builder lives in another repo, so the simple/standard/complex band names and their triggers are inferred. Worth confirming against the real builder before the FEAT-MEM-08 cutover, since the composition behaviour (A7) hangs off it.
ASSUM-007 (parity gate = zero divergence) depends on the OD-2 probe-set freeze (build-plan Day 6). If you pick a tolerance threshold instead of strict parity, the divergence scenario's last step will need a tweak.
Both are recorded as confidence: low in the manifest, so the Coach will flag them at plan time.







/feature-plan "Relay Integration" \
      --context features/relay-integration/relay-integration_summary.md




━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ FEATURE PLANNING COMPLETE — Relay Integration (FEAT-MEM-04)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Review: TASK-REV-RLY04 → Implement (Option 1)
Feature file: .guardkit/features/FEAT-MEM-04.yaml — ✓ validated, ✓ smoke-gate paths OK

Tasks (7) — tasks/backlog/relay-integration/
Wave	Tasks
1 (parallel)	RLY-001 schema · RLY-002 exception taxonomy · RLY-007 operator verify (out of band)
2 (parallel)	RLY-003 chunker · RLY-004 chunk writer
3	RLY-005 routing service (+ smoke gate pytest tests/unit -x)
4	RLY-006 MEMORY-stream handler
Diagrams in IMPLEMENTATION-GUIDE.md: data-flow (write/read), the ack-seam sequence diagram, the task-dependency graph, and §4 Integration Contracts (5 cross-task contracts incl. the episode schema, exception taxonomy, chunk namespace + embed-on-write).
AC-quality linter: 0 unverifiable acceptance criteria.
BDD oracle (R2) activated: all 32 scenarios tagged — RLY-005 (21, the routing/idempotency brain), RLY-006 (5, ack/nak/DLQ), RLY-003 (3, chunk shape), RLY-004 (3, chunk storage). RLY-001/002 are declarative definitions covered transitively by the behavioural scenarios.
Operator follow-up: 1 — TASK-RLY-007 (operator_handoff) verifies the unverified max_deliver/DLQ-subject/empty-body contract against the sibling nats-infrastructure repo (D5/D9). DLQ config is settings-driven so verified values drop in via env, no code change.
Key design decision
The whole feature hinges on the ack-after-commit seam: a pure RelayService.ingest() (zero NATS imports, unit-testable) whose clean return is the handler's only signal to ACK; a raised PoisonEpisodeError → DLQ, TransientIngestError (and any unenumerated exception) → nak/redeliver. This makes "no silent data loss" a structural property rather than a discipline. It reuses the existing DeterministicWriter, PAYLOAD_REGISTRY, and async_store_context untouched.

Next steps

guardkit feature validate FEAT-MEM-04   # ✓ already passing
/feature-build FEAT-MEM-04
One note worth flagging: 21 of 32 scenarios mapped onto RLY-005 — architecturally honest (it's the orchestration brain) but it means that task carries most of the behavioural verification load. If you'd prefer a lighter task, I can split RLY-005's structured-path and prose-path routing into two tasks before you build. Otherwise this is ready for /feature-build.







/feature-spec "Retrieval API: search with project/payload-type/domain-tag filters + vector query + token budget, default supersession exclusion, ranked composition porting guardkit job-specific context semantics, coverage scoring; probe-set evaluation harness for the 15-query retrieval-parity gate"



━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Retrieval API + Context Assembly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/retrieval-api/retrieval-api.feature
  features/retrieval-api/retrieval-api_assumptions.yaml
  features/retrieval-api/retrieval-api_summary.md

Scenarios: 31 total
  @key-example: 8    @boundary: 6
  @negative: 11      @edge-case: 12
  @smoke: 10         @regression: 6

Assumptions: 9 total
  high: 3 (auto-proceed)
  medium: 2 (Coach review recommended)
  low: 4 (human review required)

REVIEW REQUIRED: 4 low-confidence assumptions need verification
  ASSUM-001 (complexity bands), ASSUM-007 (parity pass condition),
  ASSUM-008 (empty-request handling), ASSUM-009 (over-budget memory)
  See: features/retrieval-api/retrieval-api_assumptions.yaml

Deferred: 0 scenario groups

Next steps:
  Review: features/retrieval-api/retrieval-api.feature
  Pass to feature-plan: /feature-plan "Retrieval API + Context Assembly" \
    --context features/retrieval-api/retrieval-api_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The spec is written and parser-validated. Two things worth your attention before /feature-plan:

ASSUM-001 (complexity bands) is the load-bearing unknown — the guardkit job-specific context builder lives in another repo, so the simple/standard/complex band names and their triggers are inferred. Worth confirming against the real builder before the FEAT-MEM-08 cutover, since the composition behaviour (A7) hangs off it.
ASSUM-007 (parity gate = zero divergence) depends on the OD-2 probe-set freeze (build-plan Day 6). If you pick a tolerance threshold instead of strict parity, the divergence scenario's last step will need a tweak.
Both are recorded as confidence: low in the manifest, so the Coach will flag them at plan time.







/feature-spec "Retrieval API: search with project/payload-type/domain-tag filters + vector query + token budget, default supersession exclusion, ranked composition porting guardkit job-specific context semantics, coverage scoring; probe-set evaluation harness for the 15-query retrieval-parity gate"



━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Retrieval API + Context Assembly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/retrieval-api/retrieval-api.feature
  features/retrieval-api/retrieval-api_assumptions.yaml
  features/retrieval-api/retrieval-api_summary.md

Scenarios: 31 total
  @key-example: 8    @boundary: 6
  @negative: 11      @edge-case: 12
  @smoke: 10         @regression: 6

Assumptions: 9 total
  high: 3 (auto-proceed)
  medium: 2 (Coach review recommended)
  low: 4 (human review required)

REVIEW REQUIRED: 4 low-confidence assumptions need verification
  ASSUM-001 (complexity bands), ASSUM-007 (parity pass condition),
  ASSUM-008 (empty-request handling), ASSUM-009 (over-budget memory)
  See: features/retrieval-api/retrieval-api_assumptions.yaml

Deferred: 0 scenario groups

Next steps:
  Review: features/retrieval-api/retrieval-api.feature
  Pass to feature-plan: /feature-plan "Retrieval API + Context Assembly" \
    --context features/retrieval-api/retrieval-api_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The spec is written and parser-validated. Two things worth your attention before /feature-plan:

ASSUM-001 (complexity bands) is the load-bearing unknown — the guardkit job-specific context builder lives in another repo, so the simple/standard/complex band names and their triggers are inferred. Worth confirming against the real builder before the FEAT-MEM-08 cutover, since the composition behaviour (A7) hangs off it.
ASSUM-007 (parity gate = zero divergence) depends on the OD-2 probe-set freeze (build-plan Day 6). If you pick a tolerance threshold instead of strict parity, the divergence scenario's last step will need a tweak.
Both are recorded as confidence: low in the manifest, so the Coach will flag them at plan time.










/feature-plan "Retrieval API + Context Assembly" \
    --context features/retrieval-api/retrieval-api_summary.md



✅ Feature Planning Complete — FEAT-MEM-05: Retrieval API + Context Assembly
Review: TASK-REV-RA05 (decision → Implement) · focus = all · trade-off = quality/reliability

What was created
Artifact	Path
Feature YAML	.guardkit/features/FEAT-MEM-05.yaml
Task folder (7 tasks + README + guide)	tasks/backlog/retrieval-api/
Implementation guide (3 Mermaid diagrams + §4 contracts)	IMPLEMENTATION-GUIDE.md
Review report	.claude/reviews/TASK-REV-RA05-review-report.md
BDD linkage	31 scenarios tagged in retrieval-api.feature
Tasks (complexity 7/10 · 5 waves)
Wave	Tasks
1	TASK-RA-001 — SearchRequest model + validation (declarative)
2	TASK-RA-002 — Filtered vector search core (feature, cx 7)
3	TASK-RA-003 — Token-budgeted assembly + coverage (feature)
4	TASK-RA-004 — Job-band composition ‖ TASK-RA-005 — Probe-set parity harness
5	TASK-RA-006 — Unit/security/concurrency tests ‖ TASK-RA-007 — Integration tests
Gates & validation
AC-quality linter: 0 unverifiable acceptance criteria.
Feature validation (guardkit feature validate): ✓ valid.
Smoke gate added (pytest tests/unit -x after waves 3 & 4) — validated, paths OK. Hermetic, no NAS.
Seam tests stubbed at each §4 contract boundary (SearchRequest, RankedResults, AssembledContext).
Decisions baked in (Context B)
Layered service (Option 1); harness in-feature so AC-3 is satisfiable here.
Parity: zero-divergence as a named constant (PARITY_TOLERANCE/MIN_PROBE_SET_SIZE) — OD-2 tolerance is a one-line change.
Carried open assumptions (low confidence — flagged in tasks)
ASSUM-001 bands → verify against guardkit's real builder before FEAT-MEM-08 (RA-004).
ASSUM-007 parity tolerance · ASSUM-008 reject empty request · ASSUM-009 omit oversized memory whole — implemented per spec, still need human confirmation.
Next: /feature-build FEAT-MEM-05






/feature-spec "FastMCP server module: memory_search / memory_write_payload / memory_supersede tools over the retrieval API and deterministic writer, project resources, stdio transport for Claude Desktop, replacing the Graphiti MCP; tool-contract tests"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Memory MCP Server (FEAT-MEM-06)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:
  features/memory-mcp-server/memory-mcp-server.feature
  features/memory-mcp-server/memory-mcp-server_assumptions.yaml
  features/memory-mcp-server/memory-mcp-server_summary.md

Scenarios: 31 total
  @key-example: 7    @boundary: 5
  @negative: 9       @edge-case: 13
  @smoke: 6          @regression: 3

Assumptions: 9 total
  high: 4 (auto-proceed)
  medium: 3 (Coach review recommended)
  low: 2 (human review required)

REVIEW REQUIRED: 2 low-confidence assumptions need verification
  See: features/memory-mcp-server/memory-mcp-server_assumptions.yaml
  - ASSUM-004: project resource URI = memory://projects
  - ASSUM-005: memory_supersede rejects an empty predecessor list

Deferred: 0 scenario groups

Next steps:
  Review: features/memory-mcp-server/memory-mcp-server.feature
  Pass to feature-plan: /feature-plan "Memory MCP Server" \
    --context features/memory-mcp-server/memory-mcp-server_summary.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The specification covers the three tools over the shared write path, the project resource, stdio transport, and the three FEAT-MEM-06 acceptance criteria (write-then-find an ADR end-to-end, MCP/relay byte-identical writes, graceful no-crash degradation). Two low-confidence assumptions (resource URI scheme, empty-predecessor handling) are flagged for verification before /feature-plan.







/feature-plan "Memory MCP Server" \
    --context features/memory-mcp-server/memory-mcp-server_summary.md



✅ FEATURE PLANNING COMPLETE — Memory MCP Server (FEAT-MEM-06)
Approach: FastMCP server reusing the single deterministic write path (Option 1)
Context A: All aspects · Quality/reliability · Context B: code-against-contract for MEM-05 · auto-detect execution · standard testing

Artifacts created
Artifact	Path
Feature YAML	.guardkit/features/FEAT-MEM-06.yaml
README	tasks/backlog/memory-mcp-server/README.md
Implementation guide (+ 3 Mermaid diagrams + §4 contracts)	IMPLEMENTATION-GUIDE.md
7 task files	tasks/backlog/memory-mcp-server/
BDD tags	31 scenarios tagged in memory-mcp-server.feature
Tasks & waves

Wave 1  TASK-MCP-001  scaffold + fastmcp dep + lazy lifespan      (scaffolding, 5)
Wave 2  TASK-MCP-002  tool-error / degradation envelope           (feature, 4)
Wave 3  TASK-MCP-003  memory_search          ┐                     (feature, 5)
        TASK-MCP-004  memory_write_payload   │ parallel            (feature, 6)
        TASK-MCP-005  memory_supersede       │                     (feature, 5)
        TASK-MCP-006  memory://projects      ┘                     (feature, 3, direct)
Wave 4  TASK-MCP-007  BDD suite + e2e tests                        (testing, 5)
Quality gates
AC linter: 0 unverifiable acceptance criteria.
Feature validation: ✓ valid (no intra-wave deps, all task_types valid, files resolve).
Smoke gates added: after_wave: [3, 4] → pytest tests/unit tests/bdd -x (paths verified against the repo's actual test roots; ✓ smoke-gate path validation passed).
§4 Integration Contracts: ServerContext, ToolErrorEnvelope, retrieval search(), DeterministicWriter.write/apply_supersessions — with consumer_context + seam-test stubs on the consumer tasks.
⚠️ One thing before you build
The Disconnection Alert in the guide: memory_search depends on fleet_memory.retrieval from FEAT-MEM-05, which is complete but unmerged (lives in .guardkit/worktrees/FEAT-MEM-05). TASK-MCP-003 is coded against the verified contract with its live test gated on the module landing, so the feature is buildable now — but for the end-to-end search path and parity tests, merge FEAT-MEM-05 first (/feature-complete FEAT-MEM-05).

Next: /feature-build FEAT-MEM-06 — or /task-work TASK-MCP-001 to start manually.










/feature-spec "Re-index pipeline: deterministic markdown-to-typed-payload parsers for guardkit seed modules, ADRs, review reports and task outcomes, publishing via nats-core MemoryEpisodeV1 through the live relay; idempotent full-corpus runs; backfill staging area for Fable-authored payloads with human review gate before publish"



The official gherkin parser (the same one /feature-plan Step 11 uses downstream) parses all 30 scenarios cleanly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Re-index Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:

re-index-pipeline.feature
re-index-pipeline_assumptions.yaml
re-index-pipeline_summary.md
Scenarios: 30 total

@key-example: 8    @boundary: 5
@negative: 10    @edge-case: 12
@smoke: 5      @regression: 6
Assumptions: 5 total

high: 3 (auto-proceed) — 5-min budget, backfill/staging/ location, json+payload_type routing
medium: 2 (Coach review recommended) — review-gate marker form, unrecognized-doc handling
low: 0
No REVIEW REQUIRED flag. Validated with the official gherkin parser (exit 0).

Note: the documented Step-8 backstop python -m installer.core.commands.lib.feature_spec_normalize isn't shipped in this consumer repo (it lives in the guardkit installer), so I validated directly with the same gherkin parser it wraps. No wrapped step lines were present to collapse.

Deferred: 0 scenario groups.

Two FEAT-MEM-07 acceptance criteria sit adjacent to this pipeline and are only lightly touched (one audit scenario): the stream-vs-store audit script and the probe-set parity report. Worth deciding in planning whether they belong in this feature or their own.

Next steps:

Review: re-index-pipeline.feature
Pass to feature-plan: /feature-plan "Re-index Pipeline" --context features/re-index-pipeline/re-index-pipeline_summary.md










/feature-plan "Re-index Pipeline" --context features/re-index-pipeline/re-index-pipeline_summary.md


 FEATURE PLANNING COMPLETE — FEAT-MEM-07 Re-index Pipeline
Review: TASK-REV-RIP7 · Scope: all aspects · Optimizing for: quality/reliability

What was created
📁 tasks/backlog/re-index-pipeline/ — 11 task files + README + IMPLEMENTATION-GUIDE
📄 .guardkit/features/FEAT-MEM-07.yaml — validated (✓ no intra-wave dep conflicts, all task_types valid, all paths resolved via --discover)
🔗 30/30 BDD scenarios tagged @task: in the .feature file → R2 oracle now active
🚦 smoke_gates added (pytest tests/unit after waves 4 & 6) → R3 between-wave gate active, paths validated
Key design decisions baked in
Sidecar review marker (Option 1) for the backfill gate — operator-controlled, outside payload content, self-assert-proof.
Idempotency lives downstream: no dedup logic in the pipeline; the writer's content-hash upsert keyed on natural_key satisfies every re-run/edit/concurrency scenario.
Two §4 Integration Contracts pinned (the boundary hot spots):
memory_episode_routing — content_format="json" + payload_type or it mis-routes/DLQs (seam tests on RIP-005/006).
typed_payload — guardkit hyphenated IDs (FEAT-MEM-07, ADR-SP-007) must normalize to underscores or the writer rejects them. This is the most likely silent failure; flagged in RIP-004 ACs.
AC-quality: 0 unverifiable acceptance criteria.
Execution waves (8)
[001 walker, 002 publisher] → 003 classify → 004 parsers → 005 orchestrator → [006 backfill, 007 audit, 008 parity] → 009 CLI → 010 integration tests → 011 operator run

⚠️ Operator follow-up tasks: 1
TASK-RIP-011 (operator_handoff) — AutoBuild skips it. The "< 5 min, zero-LLM, idempotent, audit 100%, parity" verification needs the live relay + NAS Postgres + real corpus + wall-clock. Run it post-merge against live infra, then /task-complete. Full checklist is in its ## Required operator follow-up block.
Scope note
AC-4 (probe-set parity) was included per your choice (TASK-RIP-008 builds the report generator reusing the existing retrieval/probe_harness.py; the live report runs in RIP-011).
Next step

/feature-build FEAT-MEM-07     # autonomous implementation — skips RIP-011 (operator_handoff)
One note: I left TASK-REV-RIP7 in tasks/backlog/ rather than moving it to a completed/ folder — your repo keeps review tasks flat in backlog/ (e.g. TASK-REV-RA05), so I matched that convention. Say the word if you'd rather it move.



