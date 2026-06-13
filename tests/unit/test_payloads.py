"""Unit tests for BasePayload conventions and validators.

Tests natural key construction, identifier validation, supersession rules,
and forward compatibility (extra="ignore"). Covers all TASK-TPR-001 acceptance criteria.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleet_memory.payloads.base import (
    BasePayload,
    IdentifierValidationError,
    SupersessionValidationError,
)


class ConcretePayload(BasePayload):
    """Concrete implementation for testing BasePayload behavior."""

    payload_type: str = "test_payload"


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
