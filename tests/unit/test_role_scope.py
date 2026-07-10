"""Unit tests for role-scoped retrieval defaults (D-WS4-6 read side, §6).

The MECHANISM is tested here; budget VALUES are ABL-006-gated placeholders and are not
asserted as tuned. Forward-compat: allowlists may name not-yet-registered types, which
must be filtered out so the SearchRequest validates.
"""

from __future__ import annotations

import pytest

from fleet_memory.payloads.registry import PAYLOAD_REGISTRY
from fleet_memory.retrieval.role_scope import (
    ROLE_PLAYER,
    ROLE_PRODUCT_OWNER,
    ROLE_QA_VERIFIER,
    ROLE_RETRIEVAL_DEFAULTS,
    role_scoped_search_request,
    role_tag,
)


class TestRoleScope:
    def test_scoped_default_adds_own_role_tag(self) -> None:
        req = role_scoped_search_request(ROLE_PRODUCT_OWNER, "study_tutor")
        assert "role:product-owner" in req.domain_tags
        assert req.token_budget == ROLE_RETRIEVAL_DEFAULTS[ROLE_PRODUCT_OWNER].token_budget

    def test_cross_role_opt_out_omits_role_tag(self) -> None:
        req = role_scoped_search_request(
            ROLE_PRODUCT_OWNER, "study_tutor", cross_role=True, query="anything"
        )
        assert not any(t.startswith("role:") for t in req.domain_tags)

    def test_unregistered_allowlist_types_are_filtered(self) -> None:
        # PO default allowlist names planning_outcome/spec_survival (not yet registered);
        # they must be dropped so the request validates against PAYLOAD_REGISTRY.
        req = role_scoped_search_request(ROLE_PRODUCT_OWNER, "study_tutor")
        assert all(pt in PAYLOAD_REGISTRY for pt in req.payload_types)
        assert "planning_outcome" not in req.payload_types  # gated, not registered
        assert "adr" in req.payload_types  # registered, survives

    def test_qa_verifier_live_verdict_filtered_until_registered(self) -> None:
        req = role_scoped_search_request(ROLE_QA_VERIFIER, "lpa_platform_poc")
        # live_verdict is gated; build_outcome is registered.
        assert "live_verdict" not in req.payload_types
        assert "build_outcome" in req.payload_types

    def test_player_unrestricted_means_empty_payload_types(self) -> None:
        req = role_scoped_search_request(ROLE_PLAYER, "study_tutor", query="x")
        assert req.payload_types == []  # empty == all registered types

    def test_explicit_budget_override(self) -> None:
        req = role_scoped_search_request(
            ROLE_PRODUCT_OWNER, "study_tutor", token_budget=999
        )
        assert req.token_budget == 999

    def test_extra_domain_tags_merged_with_role(self) -> None:
        req = role_scoped_search_request(
            ROLE_PRODUCT_OWNER, "study_tutor", domain_tags=["mode:mode_p"]
        )
        assert "mode:mode_p" in req.domain_tags
        assert "role:product-owner" in req.domain_tags

    def test_unknown_role_raises(self) -> None:
        with pytest.raises(KeyError):
            role_scoped_search_request("nonexistent-seat", "study_tutor")

    def test_role_tag_helper(self) -> None:
        assert role_tag("qa-verifier") == "role:qa-verifier"
