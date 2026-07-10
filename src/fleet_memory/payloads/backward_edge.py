"""Backward-edge episode payload models (schema contract 2026-07-07, WS4-S6/S7).

The six typed payloads that carry the factory's runtime signals — plan / approval /
deploy / live-verdict / grading / spec-survival — into fleet-memory over the existing
``memory.episode.{project_id}.{episode_type}`` relay. Each is a ``BasePayload`` subclass
registering additively; no transport, stream, or existing-payload change.

**Landing discipline (contract §0 / §5, binding).** These classes are AUTHORED here as
WS4-S7's deliverable, but a type is added to ``PAYLOAD_REGISTRY`` ONLY in the window its
producer is wired and emitting real episodes (``ReviewReportPayload`` — defined, never
produced — is the cautionary precedent). As of authoring none of the six producers are
live (forge Mode-P / gate path, forge DEPLOY/LIVE_GATE behind ``deploy.enabled=False``,
fleet-evals harness), so none are registered. ``registry.py`` documents the per-type
producer gate; ``tests/unit/test_backward_edge_payloads.py`` guards non-registration.
Field notation: ``R`` required, ``O`` optional (``| None`` default ``None`` unless
stated). Enums are ``str`` fields with a documented closed set — house practice
(``BuildOutcomePayload.status``): the wire stays forgiving, the vocabulary normative.

Domain-tag facets (``env:``/``gate:``/``role:``…) require the §2.9 read-side pattern
widening, which lands in this same S7 window (``retrieval/search_request.py``).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from fleet_memory.payloads.base import BasePayload

# A well-formed role facet: exactly `role:<seat>` (D-WS4-6 taxonomy). The seat value is
# left open (the taxonomy is "additive as seats appear", §6) but must be non-empty and
# tag-charset-safe so the widened read-side pattern can reach it.
_ROLE_TAG_PATTERN = re.compile(r"^role:[a-zA-Z0-9_-]+$")


def _has_role_tag(domain_tags: list[str]) -> bool:
    """Return True if any domain tag is a well-formed ``role:<seat>`` facet."""
    return any(_ROLE_TAG_PATTERN.match(tag) for tag in domain_tags)


class RoleAttributedPayload(BasePayload):
    """A ``BasePayload`` that requires a ``role:`` domain tag on write (D-WS4-6, §6).

    D-WS4-6 (DECIDED 2026-07-07, ACCEPTED) makes role a ``domain_tag`` taxonomy with a
    required-on-write tag for role-attributable episode types — the write-side
    enforcement seat, since ``BasePayload.domain_tags`` is otherwise unvalidated (§1).
    Role attribution cannot be reconstructed later, so it is captured from birth; tags
    compose where a namespace segment cannot (role is sometimes plural, §6).

    Applied to the role-attributable types only (§4 marks which): ``planning_outcome``,
    ``grading_outcome``, ``spec_survival``. ``approval_decision``'s role is conditional
    ("the seat whose output is gated when attributable", §4.2) so it does NOT inherit
    this mixin; ``deploy_record`` / ``live_verdict`` carry ``env:`` only.

    Read-side scoping (scoped-default-on-read) lives in ``retrieval/role_scope.py``.
    """

    @model_validator(mode="after")
    def _require_role_tag(self) -> RoleAttributedPayload:
        """Require at least one well-formed ``role:<seat>`` tag (D-WS4-6 write seat)."""
        if not _has_role_tag(self.domain_tags):
            raise ValueError(
                f"{type(self).__name__} is role-attributable (D-WS4-6) and requires at "
                f"least one 'role:<seat>' domain tag (e.g. 'role:product-owner'); "
                f"got domain_tags={self.domain_tags!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Inline sub-objects (plain models — forward-compatible like BasePayload)
# ---------------------------------------------------------------------------


class AssumptionDisposition(BaseModel):
    """One surfaced planning assumption and its human disposition (§4.1).

    The per-assumption block is first-class by design: a Modify/Reject is the
    contrastive half of a preference pair, reconstructed via the run's ``trace_ref``.
    """

    model_config = ConfigDict(extra="ignore")

    assumption_id: str  # R
    text: str | None = None  # one-line statement; full text via trace
    confidence: str  # R — closed set: low | medium | high
    # R — closed set: accepted | modified | rejected | deferred | undecided
    # (`undecided` = run terminated before decision; excluded from preference-pair harvest)
    disposition: str
    edit_delta: str | None = None  # unified diff generated→accepted (caps §2.6)
    edit_delta_ref: str | None = None  # trace pointer on overflow
    notes: str | None = None


class AssertionResult(BaseModel):
    """One live-gate assertion outcome (§4.4 — envelope field names verbatim)."""

    model_config = ConfigDict(extra="ignore")

    id: str  # R — unique only per gate script
    gate_id: str  # R
    status: str  # R — the envelope's assertion status set
    # failure attribution only; None on passing assertions:
    disposition: str | None = None  # counts | instrument | environment
    evidence_ref: str | None = None


# ---------------------------------------------------------------------------
# 4.1 planning_outcome — one row per planning run (role-attributable)
# ---------------------------------------------------------------------------


class PlanningOutcomePayload(RoleAttributedPayload):
    """Planning-run outcome — the curation-signal carrier (§4.1).

    Producer: forge Mode P at a planning run's terminal state. Identifier:
    ``NORM(correlation_id)``. Episode-id discriminator: ``terminal_state``.
    ``source_ref``: the forge SQLite ``planning_runs/{cid}`` row ref. Tags:
    ``role:product-owner``, ``mode:mode_p``.
    """

    payload_type: ClassVar[str] = "planning_outcome"

    correlation_id: str  # R — raw planning correlation id (intake-minted)
    feat_id: str | None = None  # O — Mode-P-minted FEAT id (008-006), set at handoff
    originator: str  # R — observed originating member id (Slack U…), never a config echo
    mode: str  # R — planning mode (e.g. mode_p)
    # R — closed set: planned_handoff | failed | timed_out (maps 1:1 onto the lifecycle
    # events + MP-012 TIMED_OUT ceiling; escalation is a transition, not a terminal)
    terminal_state: str
    assumption_count: int  # R — total assumptions surfaced
    assumptions: list[AssumptionDisposition]  # R — len == assumption_count
    proposal_refs: list[str] | None = None  # O
    spec_ref: str | None = None  # O — feature_spec_inputs/<cid>.md / branch at handoff
    approval_cycles_used: int | None = None  # O — cap-3 escalation visibility
    started_at: datetime  # R — run start (idea→handoff latency)
    duration_seconds: int  # R — run wall time
    # O* — required whenever any disposition != accepted (see validator):
    trace_ref: str | None = None

    @model_validator(mode="after")
    def _validate_assumptions(self) -> PlanningOutcomePayload:
        """len(assumptions) == assumption_count; trace_ref required on any non-accept."""
        if len(self.assumptions) != self.assumption_count:
            raise ValueError(
                f"assumption_count={self.assumption_count} must equal "
                f"len(assumptions)={len(self.assumptions)} (§4.1)"
            )
        # A Modify/Reject/Defer/Undecided row without its trace leaves the Phase-5
        # emitter with a diff against an unrecoverable base (§4.1 conditional-required).
        if any(a.disposition != "accepted" for a in self.assumptions) and not self.trace_ref:
            raise ValueError(
                "trace_ref is required whenever any assumption disposition != 'accepted' "
                "(§4.1): the preference-pair base is otherwise unrecoverable"
            )
        return self


# ---------------------------------------------------------------------------
# 4.2 approval_decision — one row per human gate decision (role optional)
# ---------------------------------------------------------------------------


class ApprovalDecisionPayload(BasePayload):
    """Human-gate decision (§4.2). Approver identity is the OBSERVED actor (LPA-19).

    Producer: forge gate path. Identifier (composite, §2.3):
    ``NORM(gate_id) + "_c{cycle or 1}_" + composite_hash(gate_id, correlation_id, cycle)``.
    Episode-id discriminator: ``decision``. ``source_ref``: the approval request/response
    record ref. Tags: ``gate:{gate_kind}`` + ``role:`` of the gated seat when attributable
    (conditional — this type is NOT role-required).
    """

    payload_type: ClassVar[str] = "approval_decision"

    correlation_id: str | None = None  # O† — set when the gate belongs to a planning run
    gate_id: str  # R — gate instance id (e.g. plan-{cid} approval slot)
    # R — closed set: planning_assumptions | build_approval | deploy_irreversible_edge
    #                 | merge_review | other
    gate_kind: str
    # O* — observed responder id (LPA-19); required for approved/rejected/revise, MUST be
    # None for timed_out and system-driven escalated (see validator):
    approver: str | None = None
    decision: str  # R — closed set: approved | rejected | revise | timed_out | escalated
    latency_seconds: int  # R — request-published → response-observed
    cycle: int | None = None  # O* — required for gate_kind=planning_assumptions
    escalated_to: str | None = None  # O — observed member id re-targeted to
    task_id: str | None = None  # O†
    feat_id: str | None = None  # O†
    request_ref: str | None = None  # O

    @model_validator(mode="after")
    def _validate_gate(self) -> ApprovalDecisionPayload:
        """Join obligation, LPA-19 approver conditionality, cyclic-gate cycle (§4.2)."""
        # † at least one work-item id — an unattributable gate row is an orphan.
        if not (self.correlation_id or self.feat_id or self.task_id):
            raise ValueError(
                "approval_decision requires at least one of "
                "{correlation_id, feat_id, task_id} (§4.2 join obligation)"
            )
        # * LPA-19: observed approver required on a real human decision, forbidden where
        # there is no observed responder (echoing config is exactly what LPA-19 forbids).
        if self.decision in {"approved", "rejected", "revise"} and not self.approver:
            raise ValueError(
                f"approver is required when decision={self.decision!r} "
                f"(LPA-19: the observed responder, §4.2)"
            )
        if self.decision in {"timed_out", "escalated"} and self.approver is not None:
            raise ValueError(
                f"approver MUST be None when decision={self.decision!r} — there is no "
                f"observed responder, and echoing config is forbidden (LPA-19, §4.2)"
            )
        # * the known cyclic gate: omitting cycle collapses distinct decisions onto one key.
        if self.gate_kind == "planning_assumptions" and self.cycle is None:
            raise ValueError(
                "cycle is required for gate_kind='planning_assumptions' (§4.2): "
                "the cyclic gate would otherwise collapse decisions onto one natural key"
            )
        return self


# ---------------------------------------------------------------------------
# 4.3 deploy_record — one row per deploy run (env-tagged, no role)
# ---------------------------------------------------------------------------


class DeployRecordPayload(BasePayload):
    """Deploy-run join record + pointer onto the F7 record (§4.3).

    Field names mirror the F7 deploy-record / B7 payload vocabulary verbatim (one
    vocabulary, no translation) except the pinned ``env_id`` naming (§7). Producer: forge
    DEPLOY stage (WS2 B8) on DeployComplete/DeployFailed. Identifier: ``NORM(deploy_run_id)``
    (re-deploys are distinct rows, not versions). Episode-id discriminator: ``status``.
    ``source_ref``: ``deploy_record_ref`` value. Tags: ``env:{env_id}``.
    """

    payload_type: ClassVar[str] = "deploy_record"

    correlation_id: str  # R — build/feature correlation back to planning
    feat_id: str | None = None  # O
    task_id: str | None = None  # O
    deploy_run_id: str  # R — raw forge run id for this DEPLOY stage execution
    env_id: str  # R — deploy profile env_id (naming authority pinned, §7)
    status: str  # R — closed set: complete | failed
    artifact_digest: str | None = None  # O — merged-artifact digest (sha)
    image_digests: dict[str, str] | None = None  # O — service → image digest
    deploy_record_ref: str  # R — path/ref of the committed F7 record
    deploy_profile_ref: str | None = None  # O — deploy/profile.yaml ref consumed
    runbook_ref: str | None = None  # O — the rendered typed runbook executed
    hosts: list[str] | None = None  # O — host set from the profile
    reservation_resource: str | None = None  # O — e.g. gb10-gpu (contention signal)
    failed_step: str | None = None  # O — step type at failure when status=failed
    duration_seconds: int | None = None  # O — stage wall time


# ---------------------------------------------------------------------------
# 4.4 live_verdict — one row per live-gate run (env-tagged, no role)
# ---------------------------------------------------------------------------


class LiveVerdictPayload(BasePayload):
    """Live-gate verdict (§4.4). Field names mirror the results-envelope vocabulary.

    Producer: forge LIVE_GATE stage (WS2 B8) when the results envelope returns through the
    frozen seam (stdout). The verdict enum carries instrument/environment dispositions:
    those re-run and are NEVER counted against the feature (WS2 event-flow rule).
    Identifier: ``NORM(run_id)`` (envelope-unique; immune to per-campaign attempt restarts).
    Episode-id discriminator: ``verdict``. ``source_ref``: the ``qa/gates/history/`` entry.
    Tags: ``env:{env_id}``.
    """

    payload_type: ClassVar[str] = "live_verdict"

    correlation_id: str  # R
    feat_id: str | None = None  # O — ⇐ envelope feature_id (§7)
    task_id: str | None = None  # O
    run_id: str  # R — the envelope's run id (raw)
    env_id: str  # R — ⇐ envelope target_env (§7); always present
    # R — closed set: pass | fail | instrument_fail | environment_fail:
    verdict: str
    gate_ids: list[str]  # R — gate scripts executed
    assertions: list[AssertionResult]  # R — per-assertion outcome (aggregate cap §2.6)
    evidence_index_ref: str  # R — the envelope's evidence index
    app_url: str | None = None  # O — live instance driven
    # R — 1-based, forge-side monotonic per correlation_id across all campaigns (NOT the
    # per-campaign F9 attempt number); instrument/environment re-runs increment it:
    attempt: int
    leak_sweep_findings: int | None = None  # O — count; detail stays in the evidence dir


# ---------------------------------------------------------------------------
# 4.5 grading_outcome — one row per (suite × checkpoint) graded run (role-attributable)
# ---------------------------------------------------------------------------


class GradingOutcomePayload(RoleAttributedPayload):
    """Model-grade outcome vs a pre-registered disposition (§4.5).

    Producer: fleet-evals harness. Grades run only against FROZEN instruments; the
    pre-registered PASS/FAIL bar is pinned before the run — this row records the
    comparison, it never defines the bar. ``project = fleet_evals`` (§2.2 exception —
    grades a model, not a repo). Identifier (composite, §2.3):
    ``NORM(suite_id) + "_" + composite_hash(suite_id, checkpoint_id)``. A re-grade versions
    the row; voiding is a versioned re-emit with ``voided=true``, NEVER ``supersedes``
    (self-supersession is structurally impossible + relay-hazardous, §2.8). Episode-id
    discriminator: ``verdict``. ``source_ref``: the graded ``runs/`` record path. Tags:
    ``role:{role}`` (R), ``suite:{suite_id}``, ``checkpoint:{checkpoint_id}``.
    """

    payload_type: ClassVar[str] = "grading_outcome"

    suite_id: str  # R — e.g. po-heldout-idea
    suite_frozen_sha: str  # R — the frozen suite commit
    model_id: str  # R — served/base model identity
    checkpoint_id: str  # R — content-addressed checkpoint id (§6.2 chain)
    dataset_sha: str | None = None  # O — training-dataset snapshot (null for base grades)
    adapter_ref: str | None = None  # O — adapter artifact ref (§6.2 chain)
    gguf_digest: str | None = None  # O — deployed artifact digest, when one exists
    llama_swap_entry: str | None = None  # O — serving entry name, when deployed
    per_criterion_scores: dict[str, float]  # R — criterion → score (suite-defined ids)
    verdict: str  # R — closed set: pass | fail
    pre_registered_disposition_ref: str  # R — frozen location of the PASS/FAIL bars
    rollout_count: int | None = None  # O — e.g. the 6-rollout G2b grade
    voided: bool = False  # O — true on the versioned re-emit that voids an earlier grade
    voided_reason: str | None = None  # O — e.g. wrong embed contract, contaminated sheet


# ---------------------------------------------------------------------------
# 4.6 spec_survival — spec-id → build → acceptance join (DF-008 RC1, role-attributable)
# ---------------------------------------------------------------------------


class SpecSurvivalPayload(RoleAttributedPayload):
    """The spec → build → acceptance join projection (§4.6, DF-008 RC1).

    Keyed on the Mode-P-minted FEAT id (008-006) so the join key exists from the moment a
    spec does. Single-writer rule: forge is the SOLE writer — it holds spec + build state
    and receives the acceptance edge through the frozen seam (§4.6). Lifecycle: forge
    re-emits at each edge with full known state; the writer versions it
    (v1 spec_issued → v2 build outcome → v3 acceptance). ``instrument_fail``/
    ``environment_fail`` live-verdicts never update the acceptance edge (§4.4).
    Identifier: ``NORM(spec_id)``. Episode-id discriminator: ``survival_state``.
    ``source_ref``: the forge SQLite planning-run/feature row ref. Tags: ``role:product-owner``.
    """

    payload_type: ClassVar[str] = "spec_survival"

    spec_id: str  # R — the FEAT id (raw), Mode-P-minted per 008-006
    correlation_id: str  # R — the planning correlation spine
    # R — closed set: spec_issued | building | built | accepted | died_at_build
    #                 | died_at_acceptance | superseded:
    survival_state: str
    spec_ref: str  # R — spec artifact ref (triple/branch)
    planned_at: datetime  # R — spec-issue time
    build_status: str | None = None  # O — success | failure | timeout (BuildOutcome vocab)
    build_outcome_ref: str | None = None  # O — natural key of the build_outcome row
    built_at: datetime | None = None  # O — merge/build-outcome time
    acceptance_verdict: str | None = None  # O — pass | fail (counting live-gate only)
    live_verdict_ref: str | None = None  # O — natural key of the counting live_verdict row
    accepted_at: datetime | None = None  # O — acceptance time
    edges_present: list[str]  # R — subset of ["spec","build","acceptance"] (RC1 probe)


#: The six backward-edge episode types, keyed by their canonical ``payload_type``. This is
#: a manifest of AUTHORED classes only — it is NOT a registry. Registration into
#: ``PAYLOAD_REGISTRY`` is gated per-type on producer wiring (contract §5); see
#: ``registry.py`` for the per-type producer gate and the non-registration guard test.
BACKWARD_EDGE_PAYLOADS: dict[str, type[BasePayload]] = {
    PlanningOutcomePayload.payload_type: PlanningOutcomePayload,
    ApprovalDecisionPayload.payload_type: ApprovalDecisionPayload,
    DeployRecordPayload.payload_type: DeployRecordPayload,
    LiveVerdictPayload.payload_type: LiveVerdictPayload,
    GradingOutcomePayload.payload_type: GradingOutcomePayload,
    SpecSurvivalPayload.payload_type: SpecSurvivalPayload,
}
