"""Tests for payload dispatch registry and round-trip serialization.

Validates the bijective name→model registry, round-trip determinism,
and unknown type rejection per TASK-TPR-003 acceptance criteria.
"""

from __future__ import annotations

import pytest

from fleet_memory.errors import UnknownPayloadTypeError
from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.models import (
    ADRPayload,
    BuildOutcomePayload,
    DocumentPayload,
    PatternPayload,
    ReviewReportPayload,
    SeedModulePayload,
    WarningPayload,
)
from fleet_memory.payloads.registry import (
    PAYLOAD_REGISTRY,
    get_model_for_type,
    get_type_for_model,
)


@pytest.mark.seam
@pytest.mark.integration_contract("payload_round_trip")
def test_payload_round_trip_is_deterministic():
    """A payload survives serialize -> dispatch -> rebuild unchanged.

    Contract: registry[payload_type].model_validate(model_dump(payload))
              equals the original; natural_key is byte-stable across repeats.
    Producer: TASK-TPR-002 (model classes) + TASK-TPR-001 (BasePayload)
    """
    original = ADRPayload(
        project="guardkit",
        identifier="adr_sp_007",
        source_ref="x",
        decision="Use pytest for testing",
        status="accepted",
    )
    serialized = original.model_dump()
    model = PAYLOAD_REGISTRY[original.payload_type]
    rebuilt = model.model_validate(serialized)

    assert rebuilt == original
    assert rebuilt.natural_key == original.natural_key == "adr:guardkit:adr_sp_007"


class TestRegistryCompleteness:
    """AC: review_report resolves; all seven types are registered and dispatchable."""

    def test_review_report_resolves_to_model(self):
        """'review_report' resolves to ReviewReportPayload."""
        assert PAYLOAD_REGISTRY["review_report"] is ReviewReportPayload

    @pytest.mark.parametrize(
        "payload_type,expected_model",
        [
            ("adr", ADRPayload),
            ("review_report", ReviewReportPayload),
            ("build_outcome", BuildOutcomePayload),
            ("pattern", PatternPayload),
            ("warning", WarningPayload),
            ("seed_module", SeedModulePayload),
            ("document", DocumentPayload),
        ],
    )
    def test_all_seven_types_registered(self, payload_type: str, expected_model: type):
        """All seven canonical types are registered and dispatchable."""
        assert PAYLOAD_REGISTRY[payload_type] is expected_model


class TestRegistryBijection:
    """AC: Registry is a bijection - every name maps to exactly one model."""

    def test_every_name_maps_to_exactly_one_model(self):
        """Each registered name resolves to exactly one model class."""
        models = list(PAYLOAD_REGISTRY.values())
        # Check no duplicate models
        assert len(models) == len(set(id(m) for m in models))

    def test_no_two_names_map_to_same_model(self):
        """No model class is registered under multiple names."""
        name_to_model = dict(PAYLOAD_REGISTRY)
        model_to_names = {}
        for name, model in name_to_model.items():
            if model not in model_to_names:
                model_to_names[model] = []
            model_to_names[model].append(name)

        # Every model should have exactly one name
        for model, names in model_to_names.items():
            assert len(names) == 1, f"Model {model} registered under {names}"


class TestModelToNameMapping:
    """AC: A payload reports the type name it dispatches under."""

    def test_payload_reports_its_dispatch_name(self):
        """Payload's payload_type attribute is the dispatch name."""
        adr = ADRPayload(
            project="test",
            identifier="test_001",
            source_ref="x",
            decision="test",
            status="draft",
        )
        assert adr.payload_type == "adr"
        assert PAYLOAD_REGISTRY[adr.payload_type] is ADRPayload

    def test_get_type_for_model_returns_canonical_name(self):
        """get_type_for_model() returns the canonical type name for a model."""
        assert get_type_for_model(ADRPayload) == "adr"
        assert get_type_for_model(ReviewReportPayload) == "review_report"


class TestUnknownTypeRejection:
    """AC: Unknown type lookup is rejected with error naming the type."""

    def test_unknown_type_raises_error_with_name(self):
        """Looking up 'decision_log' raises UnknownPayloadTypeError."""
        with pytest.raises(UnknownPayloadTypeError) as exc:
            get_model_for_type("decision_log")
        assert "decision_log" in str(exc.value)

    def test_case_sensitive_lookup_rejects_wrong_case(self):
        """'ADR' is rejected as unknown (case-sensitive)."""
        with pytest.raises(UnknownPayloadTypeError) as exc:
            get_model_for_type("ADR")
        assert "ADR" in str(exc.value)

    def test_registry_direct_access_raises_keyerror(self):
        """Direct dict access to unknown key raises KeyError."""
        with pytest.raises(KeyError):
            _ = PAYLOAD_REGISTRY["nonexistent"]


class TestRoundTripEquality:
    """AC: Payload serialized then rebuilt equals original with unchanged natural key."""

    @pytest.mark.parametrize(
        "payload_factory",
        [
            lambda: ADRPayload(
                project="p", identifier="i", source_ref="s", decision="d", status="a"
            ),
            lambda: ReviewReportPayload(
                project="p", identifier="i", source_ref="s", verdict="approved"
            ),
            lambda: BuildOutcomePayload(
                project="p",
                identifier="i",
                source_ref="s",
                status="success",
                duration_seconds=42,
            ),
            lambda: PatternPayload(
                project="p",
                identifier="i",
                source_ref="s",
                pattern_name="Singleton",
                category="creational",
            ),
            lambda: WarningPayload(
                project="p",
                identifier="i",
                source_ref="s",
                severity="high",
                message="test",
            ),
            lambda: SeedModulePayload(
                project="p", identifier="i", source_ref="s", module_path="src/core"
            ),
            lambda: DocumentPayload(project="p", identifier="i", source_ref="s"),
        ],
    )
    def test_round_trip_preserves_equality_and_natural_key(
        self, payload_factory: callable
    ):
        """Round-trip preserves payload equality and natural key."""
        original = payload_factory()
        serialized = original.model_dump()
        model = PAYLOAD_REGISTRY[original.payload_type]
        rebuilt = model.model_validate(serialized)

        assert rebuilt == original
        assert rebuilt.natural_key == original.natural_key


class TestRoundTripDeterminism:
    """AC: Natural key identical across repeated serialization round trips."""

    def test_repeated_round_trips_produce_identical_natural_key(self):
        """Natural key stable across multiple serialize-rebuild cycles."""
        original = ADRPayload(
            project="guardkit",
            identifier="test_adr",
            source_ref="ref",
            decision="test decision",
            status="accepted",
        )

        # First round trip
        serialized1 = original.model_dump()
        rebuilt1 = PAYLOAD_REGISTRY[original.payload_type].model_validate(serialized1)

        # Second round trip
        serialized2 = rebuilt1.model_dump()
        rebuilt2 = PAYLOAD_REGISTRY[rebuilt1.payload_type].model_validate(serialized2)

        # All natural keys should be identical
        assert rebuilt1.natural_key == original.natural_key
        assert rebuilt2.natural_key == original.natural_key


class TestWriteSurfaceEquivalence:
    """AC: Same payload produces byte-for-byte identical serialized form."""

    def test_same_payload_produces_identical_serialization(self):
        """Two instances with same data produce identical serialized output."""
        payload1 = ADRPayload(
            project="test",
            identifier="adr_001",
            source_ref="ref",
            decision="decision",
            status="accepted",
        )
        payload2 = ADRPayload(
            project="test",
            identifier="adr_001",
            source_ref="ref",
            decision="decision",
            status="accepted",
        )

        serialized1 = payload1.model_dump()
        serialized2 = payload2.model_dump()

        # Should be identical
        assert serialized1 == serialized2


class TestVersionAdvancement:
    """AC: Re-authoring with new content advances version; natural key unchanged."""

    def test_version_advance_preserves_natural_key(self):
        """Incrementing version preserves natural key."""
        v1 = ADRPayload(
            project="test",
            identifier="adr_001",
            source_ref="ref",
            decision="original decision",
            status="proposed",
            version=1,
        )
        v2 = ADRPayload(
            project="test",
            identifier="adr_001",
            source_ref="ref",
            decision="updated decision",
            status="accepted",
            version=2,
        )

        assert v1.natural_key == v2.natural_key
        assert v2.version > v1.version


class TestExtraFieldIgnored:
    """AC: Unknown extra fields in serialized input are ignored on rebuild."""

    def test_extra_fields_ignored_during_rebuild(self):
        """Unknown fields in serialized data are ignored (forward compatibility)."""
        original = ADRPayload(
            project="test",
            identifier="adr_001",
            source_ref="ref",
            decision="test",
            status="accepted",
        )
        serialized = original.model_dump()
        # Add unknown fields
        serialized["unknown_field"] = "should be ignored"
        serialized["future_feature"] = 42

        # Should rebuild without error
        model = PAYLOAD_REGISTRY[original.payload_type]
        rebuilt = model.model_validate(serialized)

        assert rebuilt == original


class TestNaturalKeyDeduplication:
    """AC: Two payloads with identical type/project/identifier produce same natural key."""

    def test_identical_coordinates_produce_same_natural_key(self):
        """Same type, project, identifier → same natural key."""
        payload1 = ADRPayload(
            project="guardkit",
            identifier="adr_001",
            source_ref="ref1",
            decision="first",
            status="accepted",
        )
        payload2 = ADRPayload(
            project="guardkit",
            identifier="adr_001",
            source_ref="ref2",  # Different metadata
            decision="second",
            status="proposed",
            version=2,
        )

        assert payload1.natural_key == payload2.natural_key
