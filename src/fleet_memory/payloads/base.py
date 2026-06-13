"""Base payload model and validators for typed payload registry.

Defines BasePayload with natural key construction, identifier validation,
and supersession rules. All concrete payload types inherit from BasePayload.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, computed_field

# Regex pattern matching existing NamespaceValidationError convention
# Allows uppercase to support identifiers like ADR_SP_007 from the feature file
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_identifier(field_name: str, value: str) -> None:
    """Validate an identifier uses underscores only.

    Args:
        field_name: Name of the field being validated
        value: The identifier value

    Raises:
        IdentifierValidationError: If invalid
    """
    if not value:
        raise IdentifierValidationError(field_name, value)
    if not IDENTIFIER_PATTERN.match(value):
        raise IdentifierValidationError(field_name, value)


class IdentifierValidationError(ValueError):
    """Raised when project or identifier contains invalid characters.

    Identifiers must use underscores only (match ^[a-z0-9_]+$), no hyphens or colons.
    Follows the same pattern as NamespaceValidationError from errors.py.
    """

    def __init__(self, field_name: str, value: str) -> None:
        """Initialize with field name and invalid value.

        Args:
            field_name: The field that failed validation (project or identifier)
            value: The invalid value that was rejected
        """
        if not value:
            super().__init__(f"{field_name} identifier is required and cannot be empty")
        else:
            super().__init__(
                f"Invalid {field_name} identifier '{value}': identifiers must use "
                f"underscores only (match ^[a-zA-Z0-9_]+$)"
            )
        self.field_name = field_name
        self.value = value


class SupersessionValidationError(ValueError):
    """Raised when supersedes contains invalid natural key references.

    Supersession references must be natural-key-shaped (three colon-separated segments)
    and cannot reference the payload's own natural key.
    """

    def __init__(self, message: str, invalid_ref: str | None = None) -> None:
        """Initialize with error message and optional invalid reference.

        Args:
            message: Human-readable error description
            invalid_ref: The invalid supersession reference (optional)
        """
        super().__init__(message)
        self.invalid_ref = invalid_ref


class BasePayload(BaseModel):
    """Base model for all typed payloads in fleet-memory.

    Defines the contract for deterministic writes: natural key construction,
    identifier validation, declared supersession, domain tags, source reference,
    and version stamp.

    All concrete payload types (TASK-TPR-002) inherit from this base.
    """

    model_config = ConfigDict(extra="ignore")  # Forward compatibility (ASSUM-009)

    # Natural key segments (ASSUM-001)
    project: str
    identifier: str

    # Optional metadata (ASSUM-005/006/007)
    domain_tags: list[str] = []
    source_ref: str  # Required provenance reference
    version: int = 1  # Monotonic version starting at 1

    # Declared supersession (ASSUM-003)
    supersedes: list[str] = []

    # Subclass must set this classvar (e.g., "adr", "epic", "rule")
    payload_type: ClassVar[str] = "base"

    def __init__(self, **data: Any) -> None:
        """Initialize payload with validation.

        Validates identifiers and supersedes before Pydantic construction
        to raise custom exceptions that can be caught directly.

        Args:
            **data: Payload field data

        Raises:
            IdentifierValidationError: If identifiers are invalid
            SupersessionValidationError: If supersedes references are malformed
        """
        # Validate project and identifier before Pydantic sees them
        if "project" in data:
            _validate_identifier("project", data["project"])
        if "identifier" in data:
            _validate_identifier("identifier", data["identifier"])

        # Validate and normalize supersedes
        if "supersedes" in data and data["supersedes"]:
            supersedes = data["supersedes"]
            # Collapse duplicates while preserving order
            seen = set()
            unique = []
            for ref in supersedes:
                if ref not in seen:
                    seen.add(ref)
                    unique.append(ref)

            # Validate natural key shape (three colon-separated segments)
            for ref in unique:
                segments = ref.split(":")
                if len(segments) != 3:
                    raise SupersessionValidationError(
                        f"Supersession reference '{ref}' is not a valid natural key: "
                        f"expected 3 colon-separated segments, got {len(segments)}",
                        invalid_ref=ref,
                    )

            data["supersedes"] = unique

        # Call parent __init__ to construct the model
        super().__init__(**data)

        # Check for self-supersession after natural_key is available
        if self.natural_key in self.supersedes:
            raise SupersessionValidationError(
                f"Payload cannot supersede itself: '{self.natural_key}' "
                f"appears in supersedes list",
                invalid_ref=self.natural_key,
            )

    @computed_field  # type: ignore[misc]
    @property
    def natural_key(self) -> str:
        """Compute natural key: <payload_type>:<project>:<identifier> (ASSUM-001).

        Returns:
            Three-segment colon-separated natural key
        """
        return f"{self.payload_type}:{self.project}:{self.identifier}"
