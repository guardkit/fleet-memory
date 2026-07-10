"""Unit tests for the six backward-edge episode payloads (schema contract 2026-07-07).

Covers §4 field specs and validators, the D-WS4-6 role-attribution write seat (§6), the
§2.3 NORM/composite-identifier helpers, and — critically — the §0/§5 landing discipline:
none of the six types may appear in PAYLOAD_REGISTRY until its producer is wired.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleet_memory.payloads.backward_edge import (
    BACKWARD_EDGE_PAYLOADS,
    ApprovalDecisionPayload,
    AssertionResult,
    AssumptionDisposition,
    DeployRecordPayload,
    GradingOutcomePayload,
    LiveVerdictPayload,
    PlanningOutcomePayload,
    RoleAttributedPayload,
    SpecSurvivalPayload,
)
from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.norm import (
    composite_hash,
    composite_identifier,
    norm,
    norm_project,
)
from fleet_memory.payloads.registry import (
    _BACKWARD_EDGE_PRODUCER_GATES,
    PAYLOAD_REGISTRY,
)

# ---------------------------------------------------------------------------
# Helpers to build valid instances
# ---------------------------------------------------------------------------


def _planning(**overrides: object) -> PlanningOutcomePayload:
    data: dict = dict(
        project="study_tutor",
        identifier=norm("cid-123"),
        source_ref="planning_runs/cid-123",
        domain_tags=["role:product-owner", "mode:mode_p"],
        correlation_id="cid-123",
        originator="U0ABC",
        mode="mode_p",
        terminal_state="planned_handoff",
        assumption_count=1,
        assumptions=[
            AssumptionDisposition(
                assumption_id="a1", confidence="high", disposition="accepted"
            )
        ],
        started_at="2026-07-07T10:00:00Z",
        duration_seconds=120,
    )
    data.update(overrides)
    return PlanningOutcomePayload(**data)


def _approval(**overrides: object) -> ApprovalDecisionPayload:
    data: dict = dict(
        project="study_tutor",
        identifier="plan_cid_123_c1_abcdef123456",
        source_ref="approval/req/1",
        gate_id="plan-cid-123",
        gate_kind="build_approval",
        approver="U0RESP",
        decision="approved",
        latency_seconds=30,
        correlation_id="cid-123",
        domain_tags=["gate:build_approval"],
    )
    data.update(overrides)
    return ApprovalDecisionPayload(**data)


def _grading(**overrides: object) -> GradingOutcomePayload:
    data: dict = dict(
        project="fleet_evals",
        identifier=composite_identifier("po-heldout-idea", "f36a866abc12"),
        source_ref="runs/2026-07-07/po-heldout.json",
        domain_tags=[
            "role:coach",
            "suite:po-heldout-idea",
            "checkpoint:f36a866abc12",
        ],
        suite_id="po-heldout-idea",
        suite_frozen_sha="f36a866",
        model_id="gemma4-po",
        checkpoint_id="f36a866abc12",
        per_criterion_scores={"clarity": 4.0, "coverage": 3.5},
        verdict="pass",
        pre_registered_disposition_ref="fleet-evals/RESULTS/po-heldout.md",
    )
    data.update(overrides)
    return GradingOutcomePayload(**data)


def _spec_survival(**overrides: object) -> SpecSurvivalPayload:
    data: dict = dict(
        project="study_tutor",
        identifier=norm("FEAT-SPL-042"),
        source_ref="planning_runs/cid-123",
        domain_tags=["role:product-owner"],
        spec_id="FEAT-SPL-042",
        correlation_id="cid-123",
        survival_state="spec_issued",
        spec_ref="feature_spec_inputs/cid-123.md",
        planned_at="2026-07-07T10:00:00Z",
        edges_present=["spec"],
    )
    data.update(overrides)
    return SpecSurvivalPayload(**data)


# ---------------------------------------------------------------------------
# Landing discipline (§0/§5) — the headline guard
# ---------------------------------------------------------------------------


class TestLandingDiscipline:
    def test_no_backward_edge_type_is_registered(self) -> None:
        """None of the six types may be in PAYLOAD_REGISTRY (no producer wired, §5).

        Registering a type without a live producer is the ReviewReportPayload mistake.
        This guard fails loudly if a future edit registers one prematurely.
        """
        for payload_type in BACKWARD_EDGE_PAYLOADS:
            assert payload_type not in PAYLOAD_REGISTRY, (
                f"{payload_type!r} was registered without a wired producer — see the "
                f"§0/§5 landing discipline in registry.py"
            )

    def test_manifest_matches_documented_producer_gates(self) -> None:
        """The authored-class manifest and the registry's producer-gate doc agree."""
        assert set(BACKWARD_EDGE_PAYLOADS) == set(_BACKWARD_EDGE_PRODUCER_GATES)

    def test_all_six_types_present(self) -> None:
        assert set(BACKWARD_EDGE_PAYLOADS) == {
            "planning_outcome",
            "approval_decision",
            "deploy_record",
            "live_verdict",
            "grading_outcome",
            "spec_survival",
        }

    def test_all_subclass_base_payload(self) -> None:
        for model in BACKWARD_EDGE_PAYLOADS.values():
            assert issubclass(model, BasePayload)


# ---------------------------------------------------------------------------
# Role-attribution write seat (D-WS4-6, §6)
# ---------------------------------------------------------------------------


class TestRoleAttribution:
    def test_role_attributable_types_use_the_mixin(self) -> None:
        for model in (
            PlanningOutcomePayload,
            GradingOutcomePayload,
            SpecSurvivalPayload,
        ):
            assert issubclass(model, RoleAttributedPayload)

    def test_non_role_types_do_not_require_role(self) -> None:
        for model in (
            ApprovalDecisionPayload,
            DeployRecordPayload,
            LiveVerdictPayload,
        ):
            assert not issubclass(model, RoleAttributedPayload)

    def test_planning_without_role_tag_rejected(self) -> None:
        with pytest.raises(ValidationError, match="role-attributable"):
            _planning(domain_tags=["mode:mode_p"])

    def test_grading_without_role_tag_rejected(self) -> None:
        with pytest.raises(ValidationError, match="role-attributable"):
            _grading(domain_tags=["suite:po-heldout-idea"])

    def test_spec_survival_without_role_tag_rejected(self) -> None:
        with pytest.raises(ValidationError, match="role-attributable"):
            _spec_survival(domain_tags=[])

    def test_malformed_role_tag_does_not_satisfy_requirement(self) -> None:
        # "role:" with no seat, or a non-role tag, must not count.
        with pytest.raises(ValidationError, match="role-attributable"):
            _planning(domain_tags=["role:", "mode:mode_p"])

    def test_valid_role_tag_accepted(self) -> None:
        p = _planning()
        assert "role:product-owner" in p.domain_tags


# ---------------------------------------------------------------------------
# 4.1 planning_outcome
# ---------------------------------------------------------------------------


class TestPlanningOutcome:
    def test_valid_all_accepted_no_trace_ref_needed(self) -> None:
        p = _planning()
        assert p.natural_key == "planning_outcome:study_tutor:cid_123"
        assert p.trace_ref is None

    def test_assumption_count_mismatch_rejected(self) -> None:
        with pytest.raises(ValidationError, match="assumption_count"):
            _planning(assumption_count=2)

    def test_trace_ref_required_on_non_accept(self) -> None:
        with pytest.raises(ValidationError, match="trace_ref"):
            _planning(
                assumptions=[
                    AssumptionDisposition(
                        assumption_id="a1", confidence="low", disposition="modified"
                    )
                ],
            )

    def test_trace_ref_present_on_non_accept_accepted(self) -> None:
        p = _planning(
            assumptions=[
                AssumptionDisposition(
                    assumption_id="a1",
                    confidence="low",
                    disposition="modified",
                    edit_delta="- old\n+ new",
                )
            ],
            trace_ref="traces/cid-123.jsonl",
        )
        assert p.trace_ref == "traces/cid-123.jsonl"

    def test_roundtrip(self) -> None:
        p = _planning()
        rebuilt = PlanningOutcomePayload.model_validate_json(p.model_dump_json())
        assert rebuilt.correlation_id == "cid-123"
        assert rebuilt.assumptions[0].disposition == "accepted"


# ---------------------------------------------------------------------------
# 4.2 approval_decision
# ---------------------------------------------------------------------------


class TestApprovalDecision:
    def test_valid_approved(self) -> None:
        a = _approval()
        assert a.decision == "approved"
        assert a.approver == "U0RESP"

    def test_join_obligation_all_ids_missing_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            _approval(correlation_id=None, feat_id=None, task_id=None)

    def test_join_satisfied_by_feat_id_alone(self) -> None:
        a = _approval(correlation_id=None, feat_id="FEAT-1")
        assert a.feat_id == "FEAT-1"

    def test_approver_required_for_human_decisions(self) -> None:
        for decision in ("approved", "rejected", "revise"):
            with pytest.raises(ValidationError, match="approver is required"):
                _approval(decision=decision, approver=None)

    def test_approver_forbidden_for_timeout_and_escalated(self) -> None:
        for decision in ("timed_out", "escalated"):
            with pytest.raises(ValidationError, match="approver MUST be None"):
                _approval(decision=decision, approver="U0RESP")

    def test_timeout_with_no_approver_accepted(self) -> None:
        a = _approval(decision="timed_out", approver=None)
        assert a.approver is None

    def test_cycle_required_for_planning_assumptions_gate(self) -> None:
        with pytest.raises(ValidationError, match="cycle is required"):
            _approval(gate_kind="planning_assumptions", cycle=None)

    def test_cycle_present_for_planning_assumptions_accepted(self) -> None:
        a = _approval(gate_kind="planning_assumptions", cycle=2)
        assert a.cycle == 2


# ---------------------------------------------------------------------------
# 4.3 / 4.4 deploy_record & live_verdict (env-tagged, no role)
# ---------------------------------------------------------------------------


class TestDeployAndLiveVerdict:
    def test_deploy_record_valid_no_role_needed(self) -> None:
        d = DeployRecordPayload(
            project="lpa_platform_poc",
            identifier=norm("deploy-run-9"),
            source_ref="deploy/records/9.json",
            domain_tags=["env:prod"],
            correlation_id="cid-9",
            deploy_run_id="deploy-run-9",
            env_id="prod",
            status="complete",
            deploy_record_ref="deploy/records/9.json",
        )
        assert d.natural_key == "deploy_record:lpa_platform_poc:deploy_run_9"
        assert d.image_digests is None

    def test_live_verdict_valid_with_assertions(self) -> None:
        v = LiveVerdictPayload(
            project="lpa_platform_poc",
            identifier=norm("run-77"),
            source_ref="qa/gates/history/run-77.json",
            domain_tags=["env:prod"],
            correlation_id="cid-9",
            run_id="run-77",
            env_id="prod",
            verdict="pass",
            gate_ids=["gate_login"],
            assertions=[
                AssertionResult(id="a1", gate_id="gate_login", status="pass")
            ],
            evidence_index_ref="qa/gates/history/run-77/index.json",
            attempt=1,
        )
        assert v.verdict == "pass"
        # green run: passing assertion carries no disposition (§4.4)
        assert v.assertions[0].disposition is None


# ---------------------------------------------------------------------------
# 4.5 grading_outcome & 4.6 spec_survival
# ---------------------------------------------------------------------------


class TestGradingAndSpecSurvival:
    def test_grading_valid_project_is_fleet_evals(self) -> None:
        g = _grading()
        assert g.project == "fleet_evals"
        assert g.voided is False
        assert g.identifier.startswith("po_heldout_idea_")

    def test_grading_voided_reemit(self) -> None:
        g = _grading(voided=True, voided_reason="contaminated sheet")
        assert g.voided is True

    def test_spec_survival_valid(self) -> None:
        s = _spec_survival()
        assert s.spec_id == "FEAT-SPL-042"
        assert s.edges_present == ["spec"]
        assert s.natural_key == "spec_survival:study_tutor:FEAT_SPL_042"


# ---------------------------------------------------------------------------
# §2.3 NORM helpers
# ---------------------------------------------------------------------------


class TestNormHelpers:
    def test_norm_replaces_non_identifier_chars(self) -> None:
        assert norm("plan-cid-123") == "plan_cid_123"
        assert norm("FEAT-SPL-042") == "FEAT_SPL_042"  # case preserved
        assert norm("a.b:c/d") == "a_b_c_d"

    def test_norm_project_lowercases(self) -> None:
        assert norm_project("Study-Tutor") == "study_tutor"

    def test_composite_hash_is_injective_over_boundaries(self) -> None:
        # The §2.3 collision case: naive concat would collide; the 0x1F join must not.
        assert composite_hash("po-heldout", "idea-x") != composite_hash(
            "po-heldout-idea", "x"
        )

    def test_composite_hash_is_deterministic_and_hex12(self) -> None:
        h = composite_hash("po-heldout-idea", "f36a866abc12")
        assert h == composite_hash("po-heldout-idea", "f36a866abc12")
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_composite_identifier_shape(self) -> None:
        ident = composite_identifier("po-heldout-idea", "f36a866abc12")
        assert ident.startswith("po_heldout_idea_")
        assert ident.rsplit("_", 1)[1] == composite_hash(
            "po-heldout-idea", "f36a866abc12"
        )
        # The composed identifier must satisfy the natural-key identifier charset.
        GradingOutcomePayload(
            project="fleet_evals",
            identifier=ident,
            source_ref="runs/x.json",
            domain_tags=["role:coach"],
            suite_id="po-heldout-idea",
            suite_frozen_sha="f36a866",
            model_id="m",
            checkpoint_id="f36a866abc12",
            per_criterion_scores={"c": 1.0},
            verdict="pass",
            pre_registered_disposition_ref="r",
        )
