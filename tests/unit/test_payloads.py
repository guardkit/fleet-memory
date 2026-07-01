"""Unit tests for BasePayload conventions and validators.

Tests natural key construction, identifier validation, supersession rules,
and forward compatibility (extra="ignore"). Covers all TASK-TPR-001 acceptance criteria.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from fleet_memory.payloads.base import (
    BasePayload,
    IdentifierValidationError,
    SupersessionValidationError,
)


class ConcretePayload(BasePayload):
    """Concrete implementation for testing BasePayload behavior."""

    payload_type: ClassVar[str] = "test_payload"


class TestNaturalKeyConstruction:
    """Test natural key format: <payload_type>:<project>:<identifier>."""

    def test_natural_key_is_three_colon_separated_segments(self) -> None:
        """Natural key has exactly three colon-separated segments (AC-001)."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
        )
        assert payload.natural_key == "test_payload:my_project:my_id"
        assert payload.natural_key.count(":") == 2


class TestIdentifierValidation:
    """Test project/identifier underscore-only validation."""

    @pytest.mark.parametrize(
        "project,identifier",
        [
            ("valid_project", "valid_id"),
            ("project123", "id456"),
            ("a_b_c", "x_y_z"),
            ("project_2026", "item_42"),
        ],
    )
    def test_valid_identifiers_with_underscores_accepted(
        self, project: str, identifier: str
    ) -> None:
        """Valid underscore-only identifiers are accepted."""
        payload = ConcretePayload(
            project=project,
            identifier=identifier,
            source_ref="test",
        )
        assert payload.project == project
        assert payload.identifier == identifier

    @pytest.mark.parametrize(
        "project,identifier,invalid_field",
        [
            ("my-project", "valid_id", "project"),
            ("valid_project", "my-id", "identifier"),
            ("ADR:SP:007", "valid_id", "project"),
            ("valid_project", "ID:INJECT", "identifier"),
        ],
    )
    def test_hyphens_and_colons_rejected_with_clear_error(
        self, project: str, identifier: str, invalid_field: str
    ) -> None:
        """Hyphens and colons in identifiers are rejected with underscore message (AC-002)."""
        with pytest.raises(IdentifierValidationError) as exc_info:
            ConcretePayload(
                project=project,
                identifier=identifier,
                source_ref="test",
            )
        error_msg = str(exc_info.value)
        assert "identifiers must use underscores" in error_msg.lower()

    def test_empty_identifier_rejected(self) -> None:
        """Empty identifier is rejected with clear error (AC-003)."""
        with pytest.raises(IdentifierValidationError) as exc_info:
            ConcretePayload(
                project="valid_project",
                identifier="",
                source_ref="test",
            )
        error_msg = str(exc_info.value)
        assert "identifier is required" in error_msg.lower()

    def test_empty_project_rejected(self) -> None:
        """Empty project is rejected with clear error."""
        with pytest.raises(IdentifierValidationError) as exc_info:
            ConcretePayload(
                project="",
                identifier="valid_id",
                source_ref="test",
            )
        error_msg = str(exc_info.value)
        assert "is required" in error_msg.lower()


class TestSupersessionValidation:
    """Test supersedes validation: natural-key-shaped references."""

    def test_valid_three_segment_references_accepted(self) -> None:
        """Valid three-segment natural key references are accepted (AC-004)."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
            supersedes=[
                "test_payload:old_project:old_id",
                "other_type:another_project:another_id",
            ],
        )
        assert len(payload.supersedes) == 2

    @pytest.mark.parametrize(
        "invalid_ref",
        [
            "only_two:segments",
            "too:many:segments:here",
            "single",
            "four:segments:are:invalid",
            "free text description",
        ],
    )
    def test_malformed_references_rejected(self, invalid_ref: str) -> None:
        """Malformed references (wrong segment count) are rejected (AC-004)."""
        with pytest.raises(SupersessionValidationError) as exc_info:
            ConcretePayload(
                project="my_project",
                identifier="my_id",
                source_ref="test",
                supersedes=[invalid_ref],
            )
        error_msg = str(exc_info.value)
        assert "not a valid natural key" in error_msg.lower()

    def test_self_supersession_rejected(self) -> None:
        """Payload cannot supersede its own natural key (AC-005, ASSUM-011)."""
        with pytest.raises(SupersessionValidationError) as exc_info:
            ConcretePayload(
                project="my_project",
                identifier="my_id",
                source_ref="test",
                supersedes=["test_payload:my_project:my_id"],
            )
        error_msg = str(exc_info.value)
        assert "cannot supersede itself" in error_msg.lower()

    def test_cross_project_supersession_accepted(self) -> None:
        """Cross-project supersession is allowed (AC-006, ASSUM-011)."""
        payload = ConcretePayload(
            project="project_a",
            identifier="my_id",
            source_ref="test",
            supersedes=["test_payload:project_b:other_id"],
        )
        assert "test_payload:project_b:other_id" in payload.supersedes

    def test_duplicate_supersession_collapsed(self) -> None:
        """Duplicate supersession references are collapsed, order-stable (AC-007)."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
            supersedes=[
                "test_payload:old_project:id1",
                "test_payload:old_project:id2",
                "test_payload:old_project:id1",  # duplicate
                "test_payload:old_project:id2",  # duplicate
            ],
        )
        # Should have exactly 2 unique references, preserving first occurrence order
        assert len(payload.supersedes) == 2
        assert payload.supersedes[0] == "test_payload:old_project:id1"
        assert payload.supersedes[1] == "test_payload:old_project:id2"

    def test_empty_supersedes_accepted(self) -> None:
        """Empty supersedes list is valid."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
            supersedes=[],
        )
        assert payload.supersedes == []


class TestDefaultValues:
    """Test default values for optional fields."""

    def test_domain_tags_defaults_to_empty(self) -> None:
        """domain_tags defaults to empty list when absent (AC-008, ASSUM-005)."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
        )
        assert payload.domain_tags == []

    def test_version_defaults_to_1(self) -> None:
        """version defaults to 1 (AC-009, ASSUM-006)."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
        )
        assert payload.version == 1

    def test_supersedes_defaults_to_empty(self) -> None:
        """supersedes defaults to empty list when absent."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
        )
        assert payload.supersedes == []


class TestForwardCompatibility:
    """Test extra="ignore" for forward compatibility."""

    def test_unknown_fields_ignored(self) -> None:
        """Unknown extra fields are silently ignored (AC-010, ASSUM-009)."""
        payload = ConcretePayload(
            project="my_project",
            identifier="my_id",
            source_ref="test",
            future_field="this_should_be_ignored",  # type: ignore[call-arg]
            another_unknown=42,  # type: ignore[call-arg]
        )
        assert payload.project == "my_project"
        assert not hasattr(payload, "future_field")
        assert not hasattr(payload, "another_unknown")


class TestRequiredFields:
    """Test that required fields are enforced."""

    def test_source_ref_required(self) -> None:
        """source_ref is required (ASSUM-007)."""
        with pytest.raises(ValidationError) as exc_info:
            ConcretePayload(  # type: ignore[call-arg]
                project="my_project",
                identifier="my_id",
            )
        assert "source_ref" in str(exc_info.value)

    def test_project_required(self) -> None:
        """project is required."""
        with pytest.raises(ValidationError) as exc_info:
            ConcretePayload(  # type: ignore[call-arg]
                identifier="my_id",
                source_ref="test",
            )
        assert "project" in str(exc_info.value)

    def test_identifier_required(self) -> None:
        """identifier is required."""
        with pytest.raises(ValidationError) as exc_info:
            ConcretePayload(  # type: ignore[call-arg]
                project="my_project",
                source_ref="test",
            )
        assert "identifier" in str(exc_info.value)


# TASK-TPR-002: Tests for seven concrete payload types
class TestConcretePayloadTypes:
    """Test the seven concrete payload type implementations."""

    def test_adr_natural_key_format(self) -> None:
        """ADR for guardkit/adr_sp_007 yields adr:guardkit:adr_sp_007 (AC-002)."""
        from fleet_memory.payloads.models import ADRPayload

        payload = ADRPayload(
            project="guardkit",
            identifier="adr_sp_007",
            source_ref="test",
            decision="Use event sourcing",
            status="accepted",
        )
        assert payload.natural_key == "adr:guardkit:adr_sp_007"
        assert payload.payload_type == "adr"

    def test_document_accepts_no_type_specific_fields(self) -> None:
        """Generic Document is accepted with no type-specific fields (AC-003)."""
        from fleet_memory.payloads.models import DocumentPayload

        payload = DocumentPayload(
            project="my_project",
            identifier="my_doc",
            source_ref="test",
        )
        assert payload.natural_key == "document:my_project:my_doc"
        assert payload.payload_type == "document"

    def test_document_content_defaults_to_none(self) -> None:
        """Back-compat: content is optional and defaults to None (metadata-only)."""
        from fleet_memory.payloads.models import DocumentPayload

        payload = DocumentPayload(
            project="my_project", identifier="my_doc", source_ref="test"
        )
        assert payload.content is None
        assert payload.model_dump()["content"] is None

    def test_document_content_prose_is_carried_and_embedded(self) -> None:
        """FEAT-MEM-09: prose content is a first-class field, present in model_dump
        (which the deterministic writer embeds) alongside domain_tags for scoped reads."""
        from fleet_memory.payloads.models import DocumentPayload

        payload = DocumentPayload(
            project="guardkit",
            identifier="project_overview_doc",
            source_ref="graphiti:project_overview:uuid",
            domain_tags=["overview"],
            content="GuardKit is an AI software factory with quality gates.",
        )
        dumped = payload.model_dump()
        assert dumped["content"] == "GuardKit is an AI software factory with quality gates."
        assert dumped["domain_tags"] == ["overview"]
        assert payload.natural_key == "document:guardkit:project_overview_doc"

    def test_review_report_requires_verdict(self) -> None:
        """ReviewReport without verdict is rejected with clear error (AC-004)."""
        from fleet_memory.payloads.models import ReviewReportPayload

        with pytest.raises(ValidationError) as exc_info:
            ReviewReportPayload(  # type: ignore[call-arg]
                project="my_project",
                identifier="review_001",
                source_ref="test",
            )
        error_msg = str(exc_info.value)
        assert "verdict" in error_msg.lower()

    def test_review_report_with_verdict_accepted(self) -> None:
        """ReviewReport with verdict is accepted."""
        from fleet_memory.payloads.models import ReviewReportPayload

        payload = ReviewReportPayload(
            project="my_project",
            identifier="review_001",
            source_ref="test",
            verdict="approved",
        )
        assert payload.natural_key == "review_report:my_project:review_001"
        assert payload.verdict == "approved"

    def test_build_outcome_payload(self) -> None:
        """BuildOutcome payload works correctly."""
        from fleet_memory.payloads.models import BuildOutcomePayload

        payload = BuildOutcomePayload(
            project="my_project",
            identifier="build_123",
            source_ref="test",
            status="success",
            duration_seconds=42,
        )
        assert payload.natural_key == "build_outcome:my_project:build_123"
        assert payload.payload_type == "build_outcome"

    def test_build_outcome_with_extended_fields(self) -> None:
        """BuildOutcome accepts task_id, lessons, approach fields (AC-001)."""
        from fleet_memory.payloads.models import BuildOutcomePayload

        payload = BuildOutcomePayload(
            project="guardkit",
            identifier="TASK_X_001",
            source_ref="test",
            status="success",
            duration_seconds=120,
            task_id="TASK-MEM08-003",
            lessons="Learned to validate extended fields in payload tests",
            approach="TDD with comprehensive test coverage",
        )
        assert payload.task_id == "TASK-MEM08-003"
        assert payload.lessons == "Learned to validate extended fields in payload tests"
        assert payload.approach == "TDD with comprehensive test coverage"
        assert payload.natural_key == "build_outcome:guardkit:TASK_X_001"

    def test_build_outcome_extended_fields_optional(self) -> None:
        """BuildOutcome extended fields are optional (AC-001 back-compat)."""
        from fleet_memory.payloads.models import BuildOutcomePayload

        # Legacy payload without extended fields should still work
        payload = BuildOutcomePayload(
            project="guardkit",
            identifier="build_456",
            source_ref="test",
            status="failure",
            duration_seconds=30,
        )
        assert payload.task_id is None
        assert payload.lessons is None
        assert payload.approach is None

    def test_build_outcome_extended_fields_in_model_dump(self) -> None:
        """Extended fields appear in model_dump for embedding (AC-002)."""
        from fleet_memory.payloads.models import BuildOutcomePayload

        payload = BuildOutcomePayload(
            project="guardkit",
            identifier="build_789",
            source_ref="test",
            status="success",
            duration_seconds=90,
            task_id="TASK-ABC-123",
            lessons="Key insight about implementation",
            approach="Iterative design approach",
        )

        dumped = payload.model_dump()
        assert dumped["task_id"] == "TASK-ABC-123"
        assert dumped["lessons"] == "Key insight about implementation"
        assert dumped["approach"] == "Iterative design approach"
        # Verify searchable content is included
        assert "Key insight" in dumped["lessons"]
        assert "Iterative design" in dumped["approach"]

    def test_build_outcome_natural_key_unchanged(self) -> None:
        """Natural key behavior unchanged with extended fields (AC-004)."""
        from fleet_memory.payloads.models import BuildOutcomePayload

        # Natural key should be build_outcome:{project}:{identifier}
        # regardless of whether extended fields are present
        payload1 = BuildOutcomePayload(
            project="guardkit",
            identifier="build_001",
            source_ref="test",
            status="success",
            duration_seconds=60,
        )

        payload2 = BuildOutcomePayload(
            project="guardkit",
            identifier="build_001",
            source_ref="test",
            status="success",
            duration_seconds=60,
            task_id="TASK-X",
            lessons="Some lessons",
            approach="Some approach",
        )

        # Same natural key despite different extended fields
        assert payload1.natural_key == payload2.natural_key
        assert payload1.natural_key == "build_outcome:guardkit:build_001"

    def test_pattern_payload(self) -> None:
        """Pattern payload works correctly."""
        from fleet_memory.payloads.models import PatternPayload

        payload = PatternPayload(
            project="my_project",
            identifier="singleton_pattern",
            source_ref="test",
            pattern_name="Singleton",
            category="creational",
        )
        assert payload.natural_key == "pattern:my_project:singleton_pattern"
        assert payload.payload_type == "pattern"

    def test_warning_payload(self) -> None:
        """Warning payload works correctly."""
        from fleet_memory.payloads.models import WarningPayload

        payload = WarningPayload(
            project="my_project",
            identifier="warn_001",
            source_ref="test",
            severity="high",
            message="Deprecated API usage detected",
        )
        assert payload.natural_key == "warning:my_project:warn_001"
        assert payload.payload_type == "warning"

    def test_seed_module_payload(self) -> None:
        """SeedModule payload works correctly."""
        from fleet_memory.payloads.models import SeedModulePayload

        payload = SeedModulePayload(
            project="my_project",
            identifier="auth_module",
            source_ref="test",
            module_path="src/auth",
        )
        assert payload.natural_key == "seed_module:my_project:auth_module"
        assert payload.payload_type == "seed_module"

    def test_all_types_inherit_base_validators(self) -> None:
        """All concrete types inherit BasePayload validators (AC-005)."""
        from fleet_memory.payloads.models import (
            ADRPayload,
            DocumentPayload,
            PatternPayload,
        )

        # Test that identifier validation is inherited
        with pytest.raises(IdentifierValidationError):
            ADRPayload(
                project="my-project-with-hyphens",
                identifier="adr_001",
                source_ref="test",
                decision="test",
                status="proposed",
            )

        # Test that supersession validation is inherited
        with pytest.raises(SupersessionValidationError):
            DocumentPayload(
                project="my_project",
                identifier="doc_001",
                source_ref="test",
                supersedes=["invalid_ref"],
            )

        # Test that domain_tags, source_ref, version, supersedes are inherited
        payload = PatternPayload(
            project="my_project",
            identifier="pattern_001",
            source_ref="test_source",
            pattern_name="Factory",
            category="creational",
            domain_tags=["design", "patterns"],
            version=2,
            supersedes=["pattern:old_project:old_pattern"],
        )
        assert payload.domain_tags == ["design", "patterns"]
        assert payload.source_ref == "test_source"
        assert payload.version == 2
        assert payload.supersedes == ["pattern:old_project:old_pattern"]
