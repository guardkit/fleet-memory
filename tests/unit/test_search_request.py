"""Unit tests for SearchRequest model and validation.

Producer: TASK-RA-001
Consumer: FEAT-MEM-05 (retrieval surface)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleet_memory.retrieval.search_request import SearchRequest


class TestSearchRequestBasicFields:
    """Test basic field types and defaults."""

    def test_minimal_valid_request(self) -> None:
        """A request with only required fields is valid."""
        req = SearchRequest(project="my_project", token_budget=1000, query="test")
        assert req.project == "my_project"
        assert req.token_budget == 1000
        assert req.payload_types == []
        assert req.domain_tags == []
        assert req.query == "test"
        assert req.include_superseded is False

    def test_all_fields_populated(self) -> None:
        """A request with all fields populated is valid."""
        req = SearchRequest(
            project="test_project",
            payload_types=["adr", "pattern"],
            domain_tags=["tag1", "tag-2"],
            query="search text",
            token_budget=500,
            include_superseded=True,
        )
        assert req.project == "test_project"
        assert req.payload_types == ["adr", "pattern"]
        assert req.domain_tags == ["tag1", "tag-2"]
        assert req.query == "search text"
        assert req.token_budget == 500
        assert req.include_superseded is True


class TestProjectValidation:
    """Test project identifier validation (scenario: hyphen project rejected)."""

    def test_project_with_hyphen_rejected(self) -> None:
        """A project filter containing a hyphen is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(project="my-project", token_budget=1000)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "project" in errors[0]["loc"]
        error_msg = str(errors[0]["msg"]).lower()
        assert "underscore" in error_msg or "identifier" in error_msg

    def test_project_with_underscore_accepted(self) -> None:
        """A project filter with underscores is accepted."""
        req = SearchRequest(project="my_project_name", token_budget=1000, query="test")
        assert req.project == "my_project_name"

    def test_project_lowercase_alphanumeric_accepted(self) -> None:
        """A project with lowercase alphanumeric characters is accepted."""
        req = SearchRequest(project="project123", token_budget=1000, query="test")
        assert req.project == "project123"


class TestPayloadTypeValidation:
    """Test payload_types validation against PAYLOAD_REGISTRY."""

    def test_unknown_payload_type_rejected(self) -> None:
        """A payload type not in PAYLOAD_REGISTRY is rejected.

        (scenario: unknown payload type rejected)
        decision_log is a valid example of an unknown type.
        """
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                payload_types=["decision_log"],
                token_budget=1000,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "payload_types" in errors[0]["loc"]
        error_msg = str(errors[0]["msg"])
        assert "decision_log" in error_msg

    def test_valid_payload_types_accepted(self) -> None:
        """All canonical payload types from PAYLOAD_REGISTRY are accepted."""
        # Test each of the seven canonical types
        canonical_types = [
            "adr",
            "review_report",
            "build_outcome",
            "pattern",
            "warning",
            "seed_module",
            "document",
        ]

        req = SearchRequest(
            project="test_project",
            payload_types=canonical_types,
            token_budget=1000,
        )
        assert req.payload_types == canonical_types

    def test_empty_payload_types_means_all(self) -> None:
        """An empty payload_types list means 'all registered types' (not 'none')."""
        req = SearchRequest(project="test_project", token_budget=1000, query="test")
        assert req.payload_types == []
        # Semantic interpretation happens in assembly, not validation

    def test_mixed_valid_and_invalid_types_rejected(self) -> None:
        """A payload_types list with any invalid type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                payload_types=["adr", "invalid_type", "pattern"],
                token_budget=1000,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "payload_types" in errors[0]["loc"]


class TestDomainTagValidation:
    """Test domain_tags validation with character-class allowlist."""

    def test_malformed_domain_tag_rejected(self) -> None:
        """A domain tag containing injection/delimiter characters is rejected.

        (scenario: malformed domain tag)
        Tags are an exact-match facet.
        """
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                domain_tags=["concurrency' OR '1'='1"],
                token_budget=1000,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "domain_tags" in errors[0]["loc"]
        error_msg = str(errors[0]["msg"]).lower()
        assert "malformed" in error_msg or "invalid" in error_msg

    def test_valid_domain_tags_accepted(self) -> None:
        """Domain tags with letters, digits, underscore, and hyphens are accepted."""
        req = SearchRequest(
            project="test_project",
            domain_tags=["tag1", "tag_2", "tag-3", "Tag-With-Hyphens"],
            token_budget=1000,
        )
        assert req.domain_tags == ["tag1", "tag_2", "tag-3", "Tag-With-Hyphens"]

    def test_domain_tag_with_quotes_rejected(self) -> None:
        """Domain tags with quotes are rejected."""
        with pytest.raises(ValidationError):
            SearchRequest(
                project="test_project",
                domain_tags=["tag'with'quotes"],
                token_budget=1000,
            )

    def test_domain_tag_with_operators_rejected(self) -> None:
        """Domain tags with SQL operators are rejected."""
        for invalid_tag in ["tag OR other", "tag AND other", "tag=value"]:
            with pytest.raises(ValidationError):
                SearchRequest(
                    project="test_project",
                    domain_tags=[invalid_tag],
                    token_budget=1000,
                )


class TestTokenBudgetValidation:
    """Test token_budget validation rules."""

    def test_negative_token_budget_rejected(self) -> None:
        """A negative token_budget is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(project="test_project", token_budget=-100)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "token_budget" in errors[0]["loc"]
        error_msg = str(errors[0]["msg"]).lower()
        assert "negative" in error_msg or "greater" in error_msg

    def test_zero_token_budget_accepted(self) -> None:
        """token_budget == 0 is accepted (assembly returns empty)."""
        req = SearchRequest(project="test_project", token_budget=0, query="test")
        assert req.token_budget == 0

    def test_positive_token_budget_accepted(self) -> None:
        """Positive token_budget is accepted."""
        req = SearchRequest(project="test_project", token_budget=5000, query="test")
        assert req.token_budget == 5000


class TestQueryOrFilterRequired:
    """Test that a query or filter is required (ASSUM-008, low confidence)."""

    def test_request_with_neither_query_nor_filter_rejected(self) -> None:
        """A request with neither query nor any filter is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(
                project="test_project",
                payload_types=[],
                domain_tags=[],
                query=None,
                token_budget=1000,
            )

        errors = exc_info.value.errors()
        # Should have a model-level validation error
        error_msg = " ".join(str(e["msg"]).lower() for e in errors)
        assert "query" in error_msg or "filter" in error_msg

    def test_request_with_query_only_accepted(self) -> None:
        """A request with only a query (no filters) is accepted."""
        req = SearchRequest(
            project="test_project",
            query="search text",
            token_budget=1000,
        )
        assert req.query == "search text"

    def test_request_with_payload_types_only_accepted(self) -> None:
        """A request with only payload_types filter (no query) is accepted."""
        req = SearchRequest(
            project="test_project",
            payload_types=["adr"],
            token_budget=1000,
        )
        assert req.payload_types == ["adr"]

    def test_request_with_domain_tags_only_accepted(self) -> None:
        """A request with only domain_tags filter (no query) is accepted."""
        req = SearchRequest(
            project="test_project",
            domain_tags=["tag1"],
            token_budget=1000,
        )
        assert req.domain_tags == ["tag1"]
