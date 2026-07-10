"""SearchRequest model and validation for retrieval surface.

Defines the typed SearchRequest for the retrieval surface and all its
input-validation rules. This is the single normalized contract every
downstream task (search core, assembly, harness) consumes.

Producer: TASK-RA-001
Consumer: FEAT-MEM-05 (search core, assembly, harness)
"""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator

from fleet_memory.payloads.registry import PAYLOAD_REGISTRY

# Project identifier pattern: lowercase alphanumeric + underscores only (no hyphens)
_PROJECT_PATTERN = re.compile(r"^[a-z0-9_]+$")

# Domain tag pattern: letters, digits, underscore, hyphen, plus exactly ONE
# optional namespace colon (exact-match facet). The optional `:segment` suffix
# admits the colon-namespaced facets the backward-edge episode contract writes
# (`env:prod`, `gate:build_approval`, `mode:mode_p`, `suite:po-heldout`,
# `checkpoint:<hex>`, `role:product-owner`) — schema contract §2.9, an
# unconditional prerequisite of that contract. Still exact-match: no quotes,
# operators, or a second colon. (backward-edge-episode-schema-contract-2026-07-07)
_DOMAIN_TAG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+)?$")


class SearchRequest(BaseModel):
    """Typed request for fleet-memory retrieval surface.

    Signature mirrored by model fields:
    search(project, payload_types, domain_tags, query, token_budget, include_superseded=False)

    All validation happens here before any vector embedding or database query.
    """

    project: str
    payload_types: list[str] = []
    domain_tags: list[str] = []
    query: str | None = None
    token_budget: int
    include_superseded: bool = False

    @field_validator("project")
    @classmethod
    def validate_project_identifier(cls, v: str) -> str:
        """Validate project uses underscores-only identifiers (no hyphens).

        Args:
            v: The project identifier

        Returns:
            The validated project identifier

        Raises:
            ValueError: If project contains hyphens or invalid characters
        """
        if not _PROJECT_PATTERN.match(v):
            raise ValueError(
                f"Project identifier '{v}' must use underscores only "
                f"(match ^[a-z0-9_]+$, no hyphens)"
            )
        return v

    @field_validator("payload_types")
    @classmethod
    def validate_payload_types(cls, v: list[str]) -> list[str]:
        """Validate payload types against PAYLOAD_REGISTRY.

        Empty list means "all registered types" (not "none").
        Semantic interpretation happens in assembly, not validation.

        Args:
            v: List of payload type names

        Returns:
            The validated payload types list

        Raises:
            ValueError: If any payload type is not in PAYLOAD_REGISTRY
        """
        unknown_types = [pt for pt in v if pt not in PAYLOAD_REGISTRY]
        if unknown_types:
            unknown_str = ", ".join(f"'{t}'" for t in unknown_types)
            raise ValueError(
                f"Unknown payload type(s) {unknown_str}: not found in PAYLOAD_REGISTRY. "
                f"Valid types: {', '.join(sorted(PAYLOAD_REGISTRY.keys()))}"
            )
        return v

    @field_validator("domain_tags")
    @classmethod
    def validate_domain_tags(cls, v: list[str]) -> list[str]:
        """Validate domain tags with character-class allowlist.

        Tags are an exact-match facet. Allowed characters: letters, digits,
        underscore, hyphen, plus exactly one optional namespace colon
        (e.g. ``env:prod``, ``role:product-owner``). No quotes, operators,
        injection characters, or a second colon.

        Args:
            v: List of domain tag strings

        Returns:
            The validated domain tags list

        Raises:
            ValueError: If any tag contains disallowed characters
        """
        malformed_tags = [tag for tag in v if not _DOMAIN_TAG_PATTERN.match(tag)]
        if malformed_tags:
            malformed_str = ", ".join(f"'{t}'" for t in malformed_tags)
            raise ValueError(
                f"Malformed domain tag(s) {malformed_str}: tags must contain only "
                f"letters, digits, underscore, or hyphen "
                f"(no quotes, operators, or injection characters)"
            )
        return v

    @field_validator("token_budget")
    @classmethod
    def validate_token_budget(cls, v: int) -> int:
        """Validate token_budget is not negative.

        Zero is accepted (assembly returns empty).

        Args:
            v: The token budget value

        Returns:
            The validated token budget

        Raises:
            ValueError: If token_budget is negative
        """
        if v < 0:
            raise ValueError(
                f"token_budget must not be negative, got {v}"
            )
        return v

    @model_validator(mode="after")
    def validate_query_or_filter_required(self) -> SearchRequest:
        """Validate that either a query or at least one filter is provided.

        ASSUM-008 (low confidence): A request with neither query nor any filter
        is rejected.

        Returns:
            The validated model instance

        Raises:
            ValueError: If neither query nor any filter is provided
        """
        has_query = self.query is not None
        has_filters = bool(self.payload_types) or bool(self.domain_tags)

        if not has_query and not has_filters:
            raise ValueError(
                "A query or at least one filter (payload_types or domain_tags) is required"
            )

        return self
