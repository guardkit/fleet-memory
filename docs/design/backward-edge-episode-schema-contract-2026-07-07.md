# Backward-Edge Episode Schema Contract

**Status:** CONTRACT-PINNED **v2** · 2026-07-07 · WS4-S6 joint with WS1-G (Fable 5, in-window) — v1 reviewed in-session by the three-lens consumer review (§8), all findings applied; **D-WS4-6 (§6) is PROPOSED for Rich, not enacted**
**Owning plans:** `ai-transition/docs/ws4-learning-flywheel-scope-and-build-plan-2026-07-07.md` §4.1 + §9 (S6 row) · `ai-transition/docs/ws1-outer-loop-completion-build-plan-2026-07-07.md` §7 (Session G, spec-survival half)
**Consumers:** WS1 planning-lifecycle sessions (E build / I), WS2 deploy + live-gate sessions (B4/B7/B8/B10), WS4 distillation + Chronicler (S7), fleet-evals grading (S4), and Rich for D-WS4-6
**Venue discipline honoured:** this session writes NO nats-core code and NO producers. Implementation homes: bus-payload/envelope deltas → WS1 Session I + WS2 B4/B7 (§7 lists their exact field obligations); fleet-memory registry models → WS4-S7; producer wiring → the sessions named per type in §5.

---

## 0. What this document is

The contract for the six backward-edge episode/payload types that carry the factory's runtime
signals (plan / approval / deploy / live-verdict / grading / spec-survival) into fleet-memory,
plus the role-memory dimension proposal (D-WS4-6). Everything rides the **existing**
`memory.episode.{project_id}.{episode_type}` relay; the six types register **additively** in the
fleet-memory payload registry. No new transport, no new streams, no change to any existing
payload type.

**The caveat that frames the investment (WS4 §6.4, carried verbatim in spirit):** retrieval
value is **UNMEASURED until ABL-006 runs**. Nothing in this contract is a retrieval bet. The
write-side schemas are justified regardless of ABL-006's outcome — they feed dataset
reconstruction, the Chronicler, and DF-008 RC1 evidence even if fleet-memory descopes to a
write-only outcome log. The only retrieval-side content here is D-WS4-6's *schema/config seat*
(§6), and its budget *values* are explicitly gated on ABL-006. (The §2.9 tag-pattern widening
is a write-reachability fix, not retrieval investment.)

**The discipline (WS4 §4.1, binding):** each payload type lands **with its producer wired, or it
is not merged**. `ReviewReportPayload` — defined 2026-07-03, zero rows ever produced — is the
cautionary precedent. §5 names the producer session for every type; a registry PR that adds a
type without its producer session landing in the same window is out of contract.

## 1. Substrate — verified ground truth this contract builds on

All checked on disk 2026-07-07 (fleet-memory main; nats-core main, read-only).

| Fact | Anchor |
|---|---|
| Envelope: `MemoryEpisodeV1` — `episode_id, project_id, episode_type, content_format, body, payload_type, source_ref, name, source, occurred_at, published_at, ingest_hints`; `extra="ignore"`; body ≤ **900 KB** (`MAX_EPISODE_BODY_BYTES`, enforced by `publish_episode`) | `nats-core/src/nats_core/events/_memory.py`; `client.py:322` |
| Subject: `memory.episode.{project_id}.{episode_type}`; `episode_type` pattern `^[a-zA-Z0-9][a-zA-Z0-9\-_]*$` | `nats-core/src/nats_core/topics.py:135` |
| Relay routing: `content_format="json"` + `payload_type` set → typed write via `PAYLOAD_REGISTRY`; **missing or unknown `payload_type` → PoisonEpisodeError → DLQ** (manual recovery) | `fleet-memory/src/fleet_memory/relay/service.py:132–135, 214–231` |
| Relay exception-map gap (for the S7 implementer): `SupersessionValidationError` is not enumerated in the relay's exception map — it falls to the default clause → transient nak-retry until max_deliver, then silent drop. §2.8 designs around it; S7 should close the gap when registering the six types | `relay/service.py:128–193`; `payloads/base.py:151–156` |
| `BasePayload`: `project, identifier, domain_tags, source_ref (required), version, supersedes`; natural key `{payload_type}:{project}:{identifier}`; **identifier charset `^[a-zA-Z0-9_]+$` — no hyphens, no colons**; `extra="ignore"` | `payloads/base.py:16, 88–103, 158–166` |
| Writer: version-aware upsert on natural key — identical content hash = no-op, changed content = version++ (content hash excludes `version`) | `writer/core.py:36, 100–124`; `writer/identity.py:54–80` |
| Retrieval scoping: 3-tuple namespace `(fleet_memory, project, payload_type)` + `domain_tags` exact-match facet; **search-side tag charset `^[a-zA-Z0-9_-]+$` — no colons**; **search-side `project` charset `^[a-z0-9_]+$` — lowercase only** | `retrieval/core.py:46–66`; `retrieval/search_request.py:20–23, 89–114` |
| Write-side `domain_tags` are **unvalidated** (plain `list[str]`) — a tag written with a colon would be stored but unreachable through `SearchRequest` until the read-side pattern widens | `payloads/base.py:95` |
| Registry today: `adr, review_report, build_outcome, pattern, warning, seed_module, document` — bijective, additive registration | `payloads/registry.py:25–33` |
| Relay image staleness drops data silently: a relay built before a field exists **silently drops** that field (`extra="ignore"`), and before a *type* exists it **poisons the episode to DLQ** | `payloads/models.py:102–105` (DocumentPayload note); `relay/service.py:132` |

**Wire-break check (gate condition):** the six types below are new registry keys only. No field
of any existing payload model changes; `BuildOutcomePayload` and `ReviewReportPayload` are
untouched; existing producers (jarvis routing-history, specialist-agent session write-back) are
unaffected. Registration is additive by construction (`PAYLOAD_REGISTRY` dict entries).

## 2. Conventions binding all six types

1. **Envelope mapping.** `episode_type` == `payload_type` (same snake_case string — both charsets
   permit it); `content_format = "json"`; `body` = the payload model's JSON
   (`model_dump_json()`); `source` = producer component id (e.g. `forge.mode_p`,
   `forge.deploy_stage`, `fleet_evals.harness`); `occurred_at` = event time at the producer;
   `source_ref` on the envelope mirrors the payload's `source_ref` (each §4 type pins what its
   `source_ref` points to — producers do not guess).
2. **`project` = the target repo of the work item** (the repo the spec/build/deploy concerns),
   normalized per rule 3 — e.g. `study_tutor`, `lpa_platform_poc`. NOT the producer's repo: the
   `project=guardkit` collapse (132/132 build_outcome rows) and the `project=specialist_agent`
   cutover collapse are the anti-patterns. Exception: `grading_outcome` grades a model, not a
   repo — its `project` = `fleet_evals` (where the graded run and RESULTS live); role
   attribution rides the `role:` tag (§6), and checkpoint identity is first-class in the payload.
3. **Identifier normalization (NORM).** `identifier` must match `^[a-zA-Z0-9_]+$`. Rule: take
   the source id (correlation_id, FEAT id, run id …) and replace every character outside
   `[a-zA-Z0-9_]` with `_`. The **`project` segment is additionally lowercased** (the search
   side requires `^[a-z0-9_]+$`; a cased project is stored but unreachable); identifier
   segments keep case (`ADR_SP_007` precedent). Raw ids — hyphens, `plan-{cid}` and all — are
   carried **unmodified** in the payload's own fields; only the natural-key segment is
   normalized. Producers MUST apply NORM deterministically so retries land on the same natural
   key (idempotency via the writer's content-hash no-op).
   **Injectivity warning:** NORM's replacement character `_` is also the natural joiner, so
   *composite* identifiers built by naive concatenation are non-injective
   (`("po-heldout", "idea-x")` and `("po-heldout-idea", "x")` collide). **Composite rule:**
   when an identifier combines ≥2 source ids, it is
   `NORM(primary_id) + "_" + hex12(SHA-256 over the raw parts joined with 0x1F)` — the hash
   disambiguates, the primary keeps rows human-greppable. §4.2 and §4.5 use this rule.
4. **Correlation spine.** Every type carries `correlation_id` (raw, as minted at planning
   intake). Per the **008-006 deviation (accepted by Rich 2026-07-07)**: forge **Mode P mints
   the correlation-linked FEAT id** — not tool-side random minting — so `feat_id` is joinable to
   `correlation_id` from birth. `spec_survival` (§4.6) is keyed on that FEAT id; every other
   type carries whichever of `correlation_id` / `feat_id` / `task_id` exists at its point in the
   lifecycle. This is the DF-008 RC1 join.
5. **Deterministic `episode_id`.** `episode_id` doubles as `Nats-Msg-Id` (JetStream dedup).
   Producers derive it as UUIDv5 over `{natural_key}|{edge-or-attempt discriminator}|r{rev}`
   (the per-type identifier rules in §4 name the discriminator; `rev` starts at 0) so a retried
   publish dedups instead of double-writing. **Corrections vs dedup:** a deliberate corrective
   re-emit inside the stream's duplicate window would otherwise dedup-drop silently — a
   correction MUST increment `rev`, which changes `episode_id` while the natural key (and thus
   the writer's versioning) is unaffected.
6. **Size discipline.** Body ≤ 900 KB is enforced at publish. Unbounded-list rules:
   `planning_outcome.assumptions[].edit_delta` ≤ 16 KB each AND ≤ 256 KB aggregate inline —
   on either overflow, truncate and set `edit_delta_ref` to the FEAT-SPL-005 trace record
   holding the full delta; `live_verdict.assertions` ≤ 256 KB aggregate — on overflow,
   truncate the list and rely on `evidence_index_ref` for the remainder. Episodes are
   join/summary records — bulk artifacts stay in traces, evidence dirs, and RESULTS files,
   referenced by `*_ref` fields.
7. **Rollout ordering (per type, hard).** (a) fleet-memory model + registry entry merged, (b)
   relay image rebuilt + redeployed, (c) only then may the producer emit. Violating (c)→(a)
   order poisons every early episode to the DLQ (manual recovery — the relay's operational
   record says treat that as an incident, not a buffer). Field *additions* to these types after
   v1 follow the same rule or the stale relay silently drops the new field. Operational
   corollary for §5's first-row gates: a test-bus emission only becomes a row if a relay
   instance **built with the new registry** is consuming that test bus.
8. **Immutability + supersession.** Episode rows are facts, not documents: producers re-emit the
   same natural key only to correct or extend (writer versions it; §2.5's `rev` rule applies).
   `supersedes` may reference **only a different natural key** — self-supersession raises at
   model construction and, per the §1 relay exception-map gap, would nak-loop and silently
   drop. Replacement-in-place is therefore modelled as a versioned re-emit with a
   type-specific voiding field (see §4.5), never via `supersedes`.
9. **Domain-tag namespacing (prerequisite, split out of D-WS4-6).** This contract's tags are
   colon-namespaced facets (`env:…`, `gate:…`, `mode:…`, `suite:…`, `checkpoint:…`, `role:…`)
   but the search-side `_DOMAIN_TAG_PATTERN` rejects colons (§1). The pattern widening to
   `^[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+)?$` (exactly one optional namespace colon; facet stays
   exact-match, no quotes/operators) is an **unconditional prerequisite of this contract** —
   `env:`/`gate:`/`suite:` need it regardless of the role-memory decision — and **lands with
   WS4-S7's registry PR at the latest**. Until it lands, producers MUST omit colon tags
   (rows remain correct; tags backfill by versioned re-emit). The `role:` tags specifically
   remain additionally conditional on D-WS4-6's enactment (§6): "R" markings on `role:` tags
   in §4 bind only after Rich files it; if the decision goes the other way, the same
   backfill-by-re-emit path applies.

## 3. Field-spec notation

`R` = required, `O` = optional (`| None`, default `None` unless stated). All models subclass
`BasePayload` (so `project, identifier, domain_tags, source_ref, version, supersedes` are
inherited and not repeated below). Enums are pinned as `str` fields with a documented closed set
— consistent with house practice (`BuildOutcomePayload.status`), leaving the wire forgiving and
the vocabulary normative.

## 4. The six types

### 4.1 `planning_outcome` — one row per planning run (the curation-signal carrier)

Producer: **forge Mode P**, at terminal state of a planning run. The per-assumption disposition
block is **first-class by design** (WS4 §2 consequence 1): when FEAT-SPL-003's per-item UX
lands, every Modify/Reject/Defer flows into the store with no further schema work — and the
`edit_delta` is the preference pair's contrastive half (WS4 §2 consequence 2). The preference-
pair reconstruction path is episode → `trace_ref` → FEAT-SPL-005 trace record (which holds the
full generated/accepted texts); hence the conditional-required rule on `trace_ref` below.

| Field | R/O | Type | Semantics |
|---|---|---|---|
| `correlation_id` | R | str | Raw planning correlation id (intake-minted) |
| `feat_id` | O | str | Mode-P-minted FEAT id (008-006) — set when the run reaches spec handoff |
| `originator` | R | str | **Observed** originating member id (the Slack `U…` id seen on the intake message — matches the FEAT-SPL-001 allowlist vocabulary), never a config echo |
| `mode` | R | str | Planning mode (e.g. `mode_p`) |
| `terminal_state` | R | str | `planned_handoff` \| `failed` \| `timed_out` — maps 1:1 onto the `planning_complete`/`planning_failed` lifecycle events + MP-012's TIMED_OUT ceiling. *Escalation is a transition, not a terminal* (threshold → re-target → ceiling → TIMED_OUT); it is visible via `approval_cycles_used` + §4.2 `escalated` rows. Additive values are anticipated for the Session-D target terminal (local spec→plan chain). **Dated deviation note vs the WS4 §4.1 sketch** (which listed `escalated`/`abandoned`): the sketch marked itself "not final"; this pin follows forge's actual state machine — 2026-07-07 |
| `assumption_count` | R | int | Total assumptions surfaced |
| `assumptions` | R | list[AssumptionDisposition] | One entry **per surfaced assumption** (`len == assumption_count`); empty only when count is 0 |
| `proposal_refs` | O | list[str] | Refs to proposal artifacts (spec triple paths, branch) |
| `spec_ref` | O | str | The `feature_spec_inputs/<cid>.md` / branch ref at PLANNED-HANDOFF |
| `approval_cycles_used` | O | int | Cycles consumed against the cap (cap-3 → escalation visibility) |
| `started_at` | R | datetime | Run start (idea→handoff latency for Session J's scope-§7 measures without a SQLite join) |
| `duration_seconds` | R | int | Run wall time |
| `trace_ref` | O* | str | FEAT-SPL-005 trace record for the run. ***Required whenever any disposition ≠ `accepted`*** — a Modify/Reject row without its trace leaves the Phase-5 emitter with a diff against an unrecoverable base |

`AssumptionDisposition` (inline object): `assumption_id: str (R)` · `text: str | None` (one-line
assumption statement; full text via trace) · `confidence: str (R)` (`low|medium|high`) ·
`disposition: str (R)` — **`accepted | modified | rejected | deferred | undecided`** (`undecided`
= run terminated before this assumption was decided — `failed`/`timed_out` terminals; excluded
from preference-pair harvest) · `edit_delta: str | None` (unified diff, proposal-as-generated →
proposal-as-accepted; caps per §2.6) · `edit_delta_ref: str | None` (trace pointer on overflow)
· `notes: str | None`.

**Disposition synonym map (binding on the bridge parser and WS1-I):** UX/bus verbs → contract
values: approve→`accepted`, edit→`modified`, reject→`rejected`, defer→`deferred`.

Identifier: `NORM(correlation_id)`. Episode-id discriminator: `terminal_state`. `source_ref`:
the forge SQLite planning-run row ref (`planning_runs/{cid}` convention). Domain tags (§2.9
gating applies): `role:product-owner`, `mode:mode_p`.

**Bridge until structured dispositions exist on the bus:** WS1-E pinned ASSUM-003 — dispositions
ride `ApprovalResponsePayload.notes` as JSON until WS1-I lands a structured field. Mode P (the
producer) parses whichever shape is live and emits the **structured** block above; the episode
contract does not inherit the interim JSON-in-notes shape.

### 4.2 `approval_decision` — one row per human gate decision

Producer: **forge gate path** (the approval-gate machinery Gate G1 proved; MP-012 escalation
included). LPA-19 rule, binding: **approver identity is the observed actor** — the member id on
the actual approval response — **never** the configured expected approver.

| Field | R/O | Type | Semantics |
|---|---|---|---|
| `correlation_id` | O† | str | Planning correlation id when the gate belongs to a planning run |
| `gate_id` | R | str | Gate instance id (e.g. the `plan-{cid}` approval slot, task gate id) |
| `gate_kind` | R | str | `planning_assumptions` \| `build_approval` \| `deploy_irreversible_edge` \| `merge_review` \| `other` |
| `approver` | O* | str | **Observed** responder member id (LPA-19). ***Required when `decision ∈ {approved, rejected, revise}`; MUST be `None` for `timed_out` and system-driven `escalated`*** — there is no observed responder, and echoing config is exactly what LPA-19 forbids |
| `decision` | R | str | `approved` \| `rejected` \| `revise` \| `timed_out` \| `escalated` |
| `latency_seconds` | R | int | Request-published → response-observed (→ timeout ceiling for `timed_out`) |
| `cycle` | O* | int | Approval cycle number (1-based). ***Required for `gate_kind = planning_assumptions`*** (the known cyclic gate) — omitting it there would collapse distinct decisions onto one natural key |
| `escalated_to` | O | str | Observed member id the gate re-targeted to (escalation path) |
| `task_id` / `feat_id` | O† | str | Whichever work-item ids exist at this gate |
| `request_ref` | O | str | Pointer to the approval request record (forge SQLite row / subject+msg id) |

† **Join obligation (model validator, WS4-S7):** at least one of
`{correlation_id, feat_id, task_id}` MUST be set — an unattributable gate row is an orphan the
Chronicler cannot attach to any feature story.

Identifier (composite rule, §2.3): `NORM(gate_id) + "_c{cycle or 1}_" +
hex12(SHA-256 over raw gate_id ⟂ correlation_id ⟂ cycle)`. Episode-id discriminator:
`decision`. `source_ref`: the approval request/response record ref (`request_ref` value).
Domain tags (§2.9 gating): `gate:{gate_kind}`, plus `role:` of the seat whose output is gated
when attributable.

### 4.3 `deploy_record` — one row per deploy run (pointer onto the F7 record)

Producer: **forge DEPLOY stage** (WS2 B8), on `DeployComplete`/`DeployFailed`. Vocabulary rule
(WS2 B7 guardrail, adopted here): field names **mirror the F7 deploy-record / B7 payload
vocabulary exactly — one vocabulary, no translation layer** (the two deliberate naming
exceptions are pinned in §7's mapping table). The episode is a join record + pointer; the F7
record stays the authority.

| Field | R/O | Type | Semantics |
|---|---|---|---|
| `correlation_id` | R | str | Build/feature correlation back to planning |
| `feat_id` / `task_id` | O | str | Work-item linkage |
| `deploy_run_id` | R | str | Raw forge run id for this DEPLOY stage execution (§2.3 rule: raw id rides the payload) |
| `env_id` | R | str | Deploy profile `env_id`. **Naming authority pinned here**: the F7 record header's `env` adopts `env_id` — dated-note obligation on B10, §7 |
| `status` | R | str | `complete` \| `failed` |
| `artifact_digest` | O | str | Merged-artifact digest (sha) |
| `image_digests` | O | dict[str, str] | service → image digest, as the B7 `DeployComplete` carries them |
| `deploy_record_ref` | R | str | Path/ref of the committed F7 record (the per-claim evidence lives there) |
| `deploy_profile_ref` | O | str | The `deploy/profile.yaml` ref consumed |
| `runbook_ref` | O | str | The rendered typed runbook executed |
| `hosts` | O | list[str] | Host set from the profile (`hosts[].host`) |
| `reservation_resource` | O | str | Reservation taken (e.g. `gb10-gpu`) — GPU-contention incidents are exactly the learning signal these rows exist to carry |
| `failed_step` | O | str | Step type at failure (`import_realm`, `health_check`, …) when `status=failed` |
| `duration_seconds` | O | int | Stage wall time |

Identifier: `NORM(deploy_run_id)` (unique per attempt — re-deploys are distinct rows, not
versions). Episode-id discriminator: `status`. `source_ref`: `deploy_record_ref` value.
Domain tags (§2.9 gating): `env:{env_id}`.

### 4.4 `live_verdict` — one row per live-gate run

Producer: **forge LIVE_GATE stage** (WS2 B8) when the results envelope returns **through the
frozen seam (stdout)** — that envelope is forge's authoritative input; the B7 bus payloads are
notifications for jarvis/WS4, never forge's trigger (§4.6 rationale). Field names mirror the
scope-design §3 results-envelope vocabulary **verbatim** (`run_id`, `gate_ids`,
`evidence_index_ref`, assertion `{id, status, evidence_ref}`); the additions the envelope does
not yet carry (`attempt`, per-assertion `disposition`) are **obligations on B4**, §7 — not
silent renames here. The verdict enum **must** carry the instrument/environment dispositions —
WS2 event-flow rule: those re-run and are **never counted against the feature**, and §4.6's
acceptance edge depends on that distinction.

| Field | R/O | Type | Semantics |
|---|---|---|---|
| `correlation_id` | R | str | Correlation back to the build |
| `feat_id` / `task_id` | O | str | Work-item linkage (`feat_id` ⇐ envelope `feature_id`, §7 mapping table) |
| `run_id` | R | str | The envelope's run id (raw) |
| `env_id` | R | str | ⇐ envelope `target_env` (§7 mapping table) — always present |
| `verdict` | R | str | `pass` \| `fail` \| `instrument_fail` \| `environment_fail` — the envelope's verdict set, four-for-four |
| `gate_ids` | R | list[str] | Gate scripts executed (F4 vocabulary: `gate_id`) |
| `assertions` | R | list[AssertionResult] | Per-assertion outcome (aggregate cap §2.6), see below |
| `evidence_index_ref` | R | str | The envelope's evidence index (F5 convention) |
| `app_url` | O | str | Live instance driven |
| `attempt` | R | int | 1-based, **forge-side monotonic per `correlation_id` across all campaigns** (F9 attempt numbers restart per campaign and are NOT this field); instrument/environment re-runs increment it |
| `leak_sweep_findings` | O | int | Count; detail stays in the envelope/evidence dir |

`AssertionResult` (envelope field names verbatim): `id: str (R)` · `gate_id: str (R)` (assertion
ids are unique only per gate script) · `status: str (R)` (the envelope's assertion status set) ·
`disposition: str | None` (`counts | instrument | environment` — failure attribution only;
`None` on passing assertions, so a green run legitimately carries no dispositions) ·
`evidence_ref: str | None`.

Identifier: `NORM(run_id)` (envelope-unique; immune to per-campaign attempt-number restarts).
Episode-id discriminator: `verdict`. `source_ref`: the envelope record ref (`qa/gates/history/`
entry). Domain tags (§2.9 gating): `env:{env_id}` (required — the source is always present).

**v1 boundary (stated, not hidden):** only **forge-dispatched** live-gate runs produce
`live_verdict` rows and acceptance edges. Operator-initiated walks (scope-design Q4) leave
envelopes in `qa/gates/history/` but no episode — a known v1 blind spot; the catch-up path is
forge re-dispatching `run_live_gate`, not a second writer.

### 4.5 `grading_outcome` — one row per (suite × checkpoint) graded run

Producer: **fleet-evals harness** (first wiring: the WS4-S4 graded run). Carries the §6.2
versioning join so "the eval history of every deployed model is queryable from the store".
Grades run only against **frozen** instruments; the pre-registered disposition is pinned
*before* the run per house retro discipline — this row records the comparison, it never
defines the bar.

| Field | R/O | Type | Semantics |
|---|---|---|---|
| `suite_id` | R | str | e.g. `po-heldout-idea` |
| `suite_frozen_sha` | R | str | The frozen suite commit (e.g. `f36a866`) |
| `model_id` | R | str | Served/base model identity |
| `checkpoint_id` | R | str | Content-addressed checkpoint id (§6.2 chain: dataset sha → base+adapter → GGUF digest → llama-swap entry) |
| `dataset_sha` | O | str | Training-dataset snapshot id (null for base-model grades) |
| `adapter_ref` | O | str | Adapter artifact ref (§6.2 chain element) |
| `gguf_digest` | O | str | Deployed artifact digest, when one exists |
| `llama_swap_entry` | O | str | Serving entry name, when deployed (§6.2 chain element) |
| `per_criterion_scores` | R | dict[str, float] | Criterion → score, criterion ids as the suite defines them |
| `verdict` | R | str | `pass` \| `fail` |
| `pre_registered_disposition_ref` | R | str | The frozen scope/RESULTS location holding the pre-registered PASS/FAIL bars |
| `rollout_count` | O | int | e.g. the 6-rollout G2b grade |
| `voided` | O | bool | `true` on the versioned re-emit that voids an earlier grade of this key (default `false`) |
| `voided_reason` | O | str | Why (e.g. wrong embed contract, contaminated sheet) |

Identifier (composite rule, §2.3): `NORM(suite_id) + "_" +
hex12(SHA-256 over raw suite_id ⟂ checkpoint_id)` — naive concatenation is non-injective
because `_` is also NORM's replacement character. A re-grade of the same (suite, checkpoint)
versions the row; **voiding is a versioned re-emit with `voided=true`, never `supersedes`**
(self-supersession is structurally impossible and relay-hazardous, §2.8). Episode-id
discriminator: `verdict`. `source_ref`: **the graded `runs/` record path** — the §5 first-row
gate compares against exactly this. `project = fleet_evals` (§2.2 exception). Domain tags
(§2.9 gating): `role:{role}` (R under D-WS4-6 — the seat this checkpoint serves),
`suite:{suite_id}`, `checkpoint:{checkpoint_id}` (checkpoint ids are content-addressed hex —
tag-charset-safe; gives the retrieval surface a checkpoint facet; full-history queries may
also go store-level, which the Chronicler does anyway).

### 4.6 `spec_survival` — the spec-id → build-outcome → acceptance-outcome join (DF-008 RC1)

The join record WS1 §7 (Session G) owes the flywheel; design was "one sentence inside
FEAT-SPL-005" until now. Keyed on the **Mode-P-minted FEAT id** (008-006) so the join key
exists from the moment a spec does.

**ADR-FLEET-001 compliance (trace-richness by default —
`forge/docs/research/ideas/ADR-FLEET-001-trace-richness.md`, cited per WS1 §7's obligation):**
this schema *narrows nothing* the ADR obliges — it adds a durable join projection on top of
full traces (FEAT-SPL-005) and full outcome rows; no divergence identified, so no ADR
amendment is required. If a later revision drops an edge or field the ADR implies, amend the
ADR with a dated note first.

**Single-writer rule (design refinement to WS1 §7's proposal, dated 2026-07-07):** WS1 §7
proposed "forge writes build outcome, WS2's live gate writes acceptance outcome". Pinned here
as: **forge is the sole writer of `spec_survival`** — it already holds spec + build state in
its SQLite projection and receives the acceptance outcome **through the frozen seam** (the
`guardkit qa live-gate` stdout results envelope, which is the LIVE_GATE stage's authoritative
input — scope-design §3; the B7 bus payloads are notifications for jarvis/WS4, never forge's
trigger, avoiding stage-already-terminal races and short-retention-stream loss). WS2's live
gate *supplies* the acceptance edge; forge projects it into the join row. Rationale: the
writer's version-aware upsert stores whole payloads — two repos writing partial states to one
natural key would race and drop each other's edges; a single writer with a local projection
cannot. (Who-provides semantics are preserved exactly; only who-*serializes* changed. Amend
the WS1 §7 sentence with a dated note, per the read-first rule there.) The §4.4 v1 boundary
applies: operator-initiated live runs do not reach forge and cannot write the v3 edge.

Lifecycle: forge (re-)emits the row at each edge with the **full known state**; the writer
versions it (v1 spec issued → v2 build outcome → v3 acceptance outcome). `live_verdict` rows
with `instrument_fail`/`environment_fail` never update the acceptance edge (§4.4 rule).

| Field | R/O | Type | Semantics |
|---|---|---|---|
| `spec_id` | R | str | The FEAT id (raw), Mode-P-minted per 008-006 |
| `correlation_id` | R | str | Planning correlation id (the spine) |
| `survival_state` | R | str | `spec_issued` \| `building` \| `built` \| `accepted` \| `died_at_build` \| `died_at_acceptance` \| `superseded` |
| `spec_ref` | R | str | Spec artifact ref (triple/branch) |
| `planned_at` | R | datetime | Spec-issue time |
| `build_status` | O | str | `success` \| `failure` \| `timeout` — vocabulary of `BuildOutcomePayload.status`, verbatim |
| `build_outcome_ref` | O | str | Natural key of the corresponding `build_outcome` row — populated only when that key rides the bus event (§7 obligation); forge never *derives* another producer's identifier scheme. When absent, the correlation spine remains the join |
| `built_at` | O | datetime | Merge/build-outcome time |
| `acceptance_verdict` | O | str | `pass` \| `fail` — from the counting live-gate verdict only |
| `live_verdict_ref` | O | str | Natural key of the counting `live_verdict` row (forge minted it — §4.4 — so it copies, not derives) |
| `accepted_at` | O | datetime | Acceptance time |
| `edges_present` | R | list[str] | Subset of `["spec","build","acceptance"]` — cheap completeness probe for the RC1 metric |

Identifier: `NORM(spec_id)`. Episode-id discriminator: `survival_state`. `source_ref`: the
forge SQLite planning-run/feature row ref. Domain tags (§2.9 gating): `role:product-owner`
(the spec's author seat).

## 5. Landing plan — producer named per type (the discipline, applied)

Registry model + entry for each type merges in fleet-memory **in the same window as its
producer wiring lands** (§0 discipline); relay redeploy precedes first emission (§2.7). WS4-S7
is the registry venue for all six models, but S7 merges a given type's registration only when
its producer row below is landing. First-row gates on a test bus require a relay built with
the new registry consuming that bus (§2.7 corollary).

| Type | Producer component | Producer wired in (session) | Registry lands | First-row gate |
|---|---|---|---|---|
| `planning_outcome` | forge Mode P terminal path | WS1-E **build** (FEAT-SPL-003 forge half — the same work that structures dispositions; §7 obligation block) | WS4-S7, gated on WS1-E build | a real Mode P run leaves a row with ≥1 non-`accepted` disposition capturable |
| `approval_decision` | forge gate path | WS1-E build (same forge task — gate path instrumented alongside) | WS4-S7, same gate | a real gate decision row carries the *observed* approver id |
| `deploy_record` | forge DEPLOY stage | WS2 **B8** | WS4-S7, gated on B8 | dry-run deploy of the fleet-memory exemplar profile (B8's own validation) emits a row on the test bus |
| `live_verdict` | forge LIVE_GATE stage | WS2 **B8** | WS4-S7, gated on B8 | the same B8 test-bus run emits a verdict row with ≥1 assertion — a synthetic gate script is acceptable (fleet-memory has no F4 gate registry; B8 authors a minimal fixture gate or the gate is restated against a fixture repo). Note: `disposition` qualifies *failures* — a green dry-run carries none, by design |
| `grading_outcome` | fleet-evals harness | WS4-S4 (first graded run; base-model interim grade after WS1-A is the earliest acceptable first row) | WS4-S7, gated on S4 wiring | the first graded `runs/` record has a matching episode row whose `source_ref` is that record's path |
| `spec_survival` | forge (sole writer, §4.6) | spec edge: WS1-E build · build edge: same forge path on BuildOutcome · acceptance edge: WS2 B8 seam-envelope projection | WS4-S7, first two edges may land before B8 | one FEAT id shows v1→v2 versioning from a real run; v3 joins when B8 ships |

**nats-core is untouched by the six types themselves** — they are fleet-memory payloads riding
the existing `MemoryEpisodeV1`. What the bus/envelope sessions owe is listed in §7.

## 6. D-WS4-6 — role-memory dimension · **PROPOSED 2026-07-07, for Rich (do not enact)**

**Decision:** role as a **`domain_tag` taxonomy**, not a namespace segment. No pgvector
namespace migration; the 3-tuple `(fleet_memory, project, payload_type)` stays as-is.
*(The tag-charset widening that colon tags require is NOT part of this decision — it is a
contract prerequisite in its own right, §2.9, needed by `env:`/`gate:`/`suite:` regardless of
how this decision goes. D-WS4-6 decides only the role dimension and budgets below.)*

- **Tag taxonomy:** `role:product-owner`, `role:architect`, `role:coach`, `role:qa-verifier`,
  `role:player` (one per §5-table seat; additive as seats appear).
- **Enforcement seat (named so the decision is costed):** required-on-write is a **model
  validator on the six new payload classes** (write-side `domain_tags` is otherwise
  unvalidated, §1) — a small fleet-memory code change landing with WS4-S7, applied to types
  where the row is role-attributable (§4 marks which). Read side: scoped-default-on-read — a
  role's harness passes its own `role:` tag by default and must *opt out* to read cross-role.
- **Per-role retrieval budgets:** a per-role default `token_budget` (+ default
  `payload_types` allowlist) in each role's harness config — the PO does not need the Coach's
  build-outcome firehose. Illustrative seat defaults (config seat is the deliverable; **values
  are placeholders until ABL-006** — WS4 §6.4 gate, no retrieval-side tuning before it
  reports): PO 4000 tokens / `{adr, planning_outcome, spec_survival, document}`; Architect
  4000 / `{adr, pattern, build_outcome}`; Coach 2500 / `{build_outcome, review_report,
  warning}`; QA-Verifier 1500 / `{live_verdict, build_outcome}`; Player 6000 / unrestricted.
- **Why not a namespace segment:** a 4-tuple namespace is a store migration + relay/writer/
  retrieval change across every existing row for a benefit (role scoping) the tag facet already
  delivers; and role attribution is sometimes plural (a spec row is PO-authored but
  architect-consumed) — tags compose, namespace segments don't.
- **If deferred or decided otherwise:** producers simply keep omitting `role:` tags (§2.9);
  rows stay correct and retag by versioned re-emit — no schema debt accrues either way.
- **What this does NOT decide:** budget values, RAG re-enablement, any memory-heavy harness
  feature — all ABL-006-gated (WS4 §6.4).

## 7. Obligations on the bus, envelope, and producer sessions

The six episode types need these fields/actions to exist so producers can populate §4 without
side-channels. This section is the input to those sessions — no code here.

**Deliberate naming exceptions (the only two; everything else mirrors verbatim):**

| Episode field | Source name | Why the episode name wins |
|---|---|---|
| `feat_id` | envelope `feature_id` | 008-006 fleet naming — the Mode-P-minted FEAT id is the cross-workstream join key |
| `env_id` | envelope `target_env` / F7 header `env` | the deploy profile is the source of truth; B10 dated-note obligation below aligns F7 |

**WS1 Session I (nats-core):**
1. Structured per-assumption dispositions on the approval response (replacing the ASSUM-003
   JSON-in-`notes` bridge): a field carrying
   `[{assumption_id, disposition, edit_delta?, notes?}]` with the §4.1 disposition vocabulary
   and synonym map verbatim — or a filed dated deviation back into the FEAT-SPL-003 manifest
   per WS1 §9's rule. **This is a NEW fifth item for Session I** (anticipated by ASSUM-003's
   "until a structured field lands here" but not on §9's four-item list) — append a dated note
   to WS1 §9 recording the addition.
2. The spec-ready handoff event (item 1 there) must carry `correlation_id` **and** the
   Mode-P-minted `feat_id` (008-006) plus output refs — jarvis and WS2 consume it;
   `spec_survival`'s v1 edge is written from forge's own state (forge emits that event, it
   does not need to read it back).
3. `planning_started/complete/failed` lifecycle events carry `correlation_id`, `mode`,
   `originator` (observed member id) — `planning_outcome.terminal_state` maps 1:1 onto
   complete/failed (+ the MP-012 timeout ceiling).
4. The `plan-{cid}` approval-topic convention documented as normative (item 2 there) —
   `approval_decision.gate_id` cites it.
5. Where a `BuildOutcome`-class bus event exists/lands, it should carry the corresponding
   `build_outcome` **natural key** so forge can *copy* `spec_survival.build_outcome_ref`
   rather than re-derive another producer's identifier scheme.
   *(WS1 §9 items 3 (NotificationPayload fields) and 4 (originating_adapter fix) have no
   episode dependency — noted only so §9's list stays whole; nothing here supersedes them.)*

**WS1-E build, forge half (producer obligations — flag as a dated amendment to the SPL-003
`_summary.md` §Forge Half note, which currently covers only thread anchor / cycle number /
revision assembler):**
6. Wire the `planning_outcome` producer at Mode P's terminal path (§4.1), the
   `approval_decision` producer at the gate path (§4.2), and the `spec_survival` v1/v2 edges
   (§4.6) — per §5, the corresponding registry entries do not merge until this lands.

**WS2 B4 (guardkit — owner of the results envelope; without these, B7 deadlocks against its
own mirror-the-envelope guardrail):**
7. Envelope grows `attempt` (as defined in §4.4 — forge-side monotonic per correlation, or
   B4/B8 agree where the counter lives) and per-assertion `disposition`. Attribution mapping
   pinned: `counts` ⇐ attribution ∈ {app, backend, contract_gap}; `instrument` ⇐ instrument;
   `environment` ⇐ environment.

**WS2 B7 (nats-core):**
8. `DeployComplete/Failed`: `env_id`, `artifact_digest`, `image_digests`, `deploy_record_ref`,
   `correlation_id`, and the failing step type on `Failed` — §4.3 mirrors these names verbatim
   (`failed_step` is a genuine addition to B7's current work list).
9. `QAVerdictPayload`/`LiveGateResultPayload`: mirror the (B4-extended) envelope — verdict enum
   includes `instrument_fail`/`environment_fail`; per-assertion results carry `disposition`;
   `evidence_index_ref`, `app_url`, `run_id`, `attempt`, `correlation_id`. §4.4 mirrors these,
   and §4.6's acceptance edge filters on them. (Remember: these payloads are notifications —
   forge's authoritative input stays the seam stdout envelope, §4.6.)
10. Capability-taxonomy entries (`deploy-runner`/`live-gate-driver`/`qa-verifier`) — no episode
    dependency, noted only so B7's list stays whole.

**WS2 B10 (guardkit — F7 schema author):**
11. F7 record header adopts `env_id` (today sketched as `env`) — dated note at authoring time,
    so B7's mirror rule has one authority (§4.3).

**WS4-S7 (fleet-memory):** the six `BasePayload` subclasses + registry entries per §5's gating;
the §4.2 at-least-one-join model validator; the §6 role-tag validator if D-WS4-6 is enacted;
the `_DOMAIN_TAG_PATTERN` widening (§2.9 — unconditional); close the relay
`SupersessionValidationError` exception-map gap (§1); relay redeploy per §2.7. The Chronicler
consumes `memory.episode.>` and the durable store — never transient notification subjects
(JARVIS stream expires 1h/1000 msgs; WS4 §4.2 caveat).

## 8. Review record — three-lens consumer review, 2026-07-07 (gate: PASSED)

Gate (WS4 §9 S6 row): schema doc reviewed against all three consumer workstreams' emission
lists; no wire break for existing producers. Executed in-session against v1 of this doc: three
independent reviewer agents, one per consuming workstream, each instructed to adversarially
verify its emission list maps cleanly. **All findings applied in this v2** before first commit
(v1 never committed; the per-lens rows below are the disposition record).

| Lens | Verdict on mappings | Findings (applied) |
|---|---|---|
| **WS1** (planning lifecycle, Sessions E/G/I) | Confirmed clean: lifecycle→`planning_outcome`, dispositions + ASSUM-003 bridge, `plan-{cid}`/cap-3/escalation→`approval_decision`, Session-G join→`spec_survival`, 008-006 key usage, single-writer refinement sound | 5 MAJOR + 6 MINOR + 4 NOTE: `terminal_state` re-pinned to forge's real terminals (`failed` added; `escalated`/`abandoned` removed with dated deviation note); `approver` conditional (LPA-19 on timeouts); `undecided` disposition added; colon-tag gating (→§2.9); WS1-E forge-half obligation block added (§7.6); Session-I item flagged as new item 5; synonym map; ADR-FLEET-001 citation; `cycle` required on cyclic gates; per-type `source_ref` pins; §9-completeness note; corrections-vs-dedup `rev` rule; §7.2 reworded; `started_at`/`duration_seconds` added |
| **WS2** (deploy/live-gate, B4/B7/B8/B10) | Confirmed clean: deploy-event mirror, verdict enum four-for-four, evidence refs, attempt semantics, single-writer consistency with B8, capability entries, `failed_step` as a correctly-placed B7 delta, `deploy_irreversible_edge` anticipation, §5 sequencing | 1 BLOCKER + 8 MAJOR + 4 MINOR + 3 NOTE: **B4 envelope obligation added** (`attempt` + per-assertion `disposition` with pinned attribution mapping — the episode no longer obligates B7 to mirror fields the envelope lacks); envelope vocabulary adopted verbatim (`run_id`, `gate_ids`, `evidence_index_ref`, assertion `{id, gate_id, status, disposition, evidence_ref}`); `live_verdict` keyed on `NORM(run_id)` (campaign-restart collision killed); `deploy_run_id` field added; `env_id` authority pinned + B10 obligation; live-verdict first-row gate restated (synthetic gate; green runs carry no dispositions); acceptance-edge channel pinned to the seam stdout envelope; operator-initiated-run v1 blind spot stated; `deploy_profile_ref`/`hosts`/`reservation_resource` added; assertions aggregate cap; naming-exception table (`feat_id`, `env_id`); test-bus relay corollary |
| **WS4** (distillation/Chronicler/D-WS4-6) | Confirmed clean: curation-signal vocabulary + first-row gate, §6.2 versioning chain, Chronicler joinability via the correlation/feat spine + instrument/environment firewall, §4.2-constraint honoured (durable store, never transient subjects), discipline (§5 producers + ReviewReportPayload precedent), D-WS4-6 packet filable | 5 MAJOR + 6 MINOR + 2 NOTE: composite-identifier injectivity rule (§2.3 hash rule; applied §4.2/§4.5); voided-grade supersession replaced with versioned re-emit + `voided` field (self-supersession impossible; relay exception-map gap recorded §1 + S7 obligation); at-least-one-join validator on `approval_decision`; `trace_ref` required when any disposition ≠ accepted (+ `text` on AssumptionDisposition); role-tag conditionality + backfill story (§2.9/§6); project-segment lowercasing in NORM; `env_id` on `live_verdict`; `checkpoint:` tag facet; `source_ref` = graded `runs/` path + `adapter_ref`/`llama_swap_entry`; enforcement seat named (model validator); aggregate delta bound; bus-carried `build_outcome` natural key (§7.5) |

Convergent finding (all three lenses, treated as the review's headline): **colon-namespaced
tags depended on an un-enacted proposal** — resolved by splitting the `_DOMAIN_TAG_PATTERN`
widening out of D-WS4-6 into §2.9 as an unconditional contract prerequisite, with `role:` tags
alone remaining D-WS4-6-conditional and a backfill-by-re-emit story either way.

**No-wire-break re-confirmed by all three lenses:** additive registry keys only; existing
producers and payload models untouched.

---

*Dated-note discipline applies: supersede sections with banners, never silent edits. This
contract does not reopen any DF-xxx decision; D-WS4-6 (§6) awaits Rich's filing.*
