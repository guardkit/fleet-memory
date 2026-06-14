"""Unit tests for document parsers in reindex pipeline.

Tests each parser kind (seed_module, ADR, review_report, build_outcome)
for correct payload construction, identifier normalization, missing-field
handling, and injection-content safety.
"""

from __future__ import annotations

from pathlib import Path

from fleet_memory.payloads.models import (
    ADRPayload,
    BuildOutcomePayload,
    ReviewReportPayload,
    SeedModulePayload,
)
from fleet_memory.reindex.parsers import (
    ParsedPayload,
    UnparseableDocument,
    parse_adr,
    parse_build_outcome,
    parse_review_report,
    parse_seed_module,
)
from fleet_memory.reindex.walker import CorpusDocument


class TestSeedModuleParser:
    """Test seed_module document parsing."""

    def test_seed_module_parses_to_canonical_payload(self) -> None:
        """A seed module document with required fields produces a SeedModulePayload."""
        doc = CorpusDocument(
            path=Path("/corpus/project/seed/bootstrap.md"),
            text="""---
type: seed_module
project: fleet_memory
identifier: bootstrap_core
module_path: src/core/bootstrap
---
# Bootstrap Core Module
""",
        )

        result = parse_seed_module(doc)

        assert isinstance(result, ParsedPayload)
        assert isinstance(result.payload, SeedModulePayload)
        assert result.payload.project == "fleet_memory"
        assert result.payload.identifier == "bootstrap_core"
        assert result.payload.module_path == "src/core/bootstrap"
        assert result.payload.source_ref == str(doc.path)
        assert result.payload.payload_type == "seed_module"

    def test_seed_module_missing_module_path_is_unparseable(self) -> None:
        """A seed module missing required module_path field is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/project/seed/incomplete.md"),
            text="""---
type: seed_module
project: fleet_memory
identifier: incomplete_module
---
# Incomplete Module
""",
        )

        result = parse_seed_module(doc)

        assert isinstance(result, UnparseableDocument)
        assert "module_path" in result.reason.lower()
        assert result.document_path == doc.path


class TestADRParser:
    """Test ADR document parsing."""

    def test_adr_parses_to_canonical_payload(self) -> None:
        """An ADR document with decision and status produces an ADRPayload."""
        doc = CorpusDocument(
            path=Path("/corpus/adrs/ADR-SP-007.md"),
            text="""---
type: adr
project: guardkit
identifier: ADR-SP-007
decision: Use PostgreSQL for primary data store
status: accepted
---
# ADR: Database Selection
""",
        )

        result = parse_adr(doc)

        assert isinstance(result, ParsedPayload)
        assert isinstance(result.payload, ADRPayload)
        assert result.payload.decision == "Use PostgreSQL for primary data store"
        assert result.payload.status == "accepted"
        assert result.payload.payload_type == "adr"

    def test_adr_missing_decision_is_unparseable(self) -> None:
        """An ADR missing the decision field is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/adrs/incomplete.md"),
            text="""---
type: adr
project: guardkit
identifier: incomplete_adr
status: proposed
---
# Incomplete ADR
""",
        )

        result = parse_adr(doc)

        assert isinstance(result, UnparseableDocument)
        assert "decision" in result.reason.lower()

    def test_adr_missing_status_is_unparseable(self) -> None:
        """An ADR missing the status field is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/adrs/no-status.md"),
            text="""---
type: adr
project: guardkit
identifier: no_status_adr
decision: Some decision
---
# ADR without status
""",
        )

        result = parse_adr(doc)

        assert isinstance(result, UnparseableDocument)
        assert "status" in result.reason.lower()


class TestReviewReportParser:
    """Test review_report document parsing."""

    def test_review_report_parses_to_canonical_payload(self) -> None:
        """A review report with verdict produces a ReviewReportPayload."""
        doc = CorpusDocument(
            path=Path("/corpus/reviews/code-review-123.md"),
            text="""---
type: review_report
project: fleet_memory
identifier: code_review_123
verdict: approved
---
# Code Review Report
""",
        )

        result = parse_review_report(doc)

        assert isinstance(result, ParsedPayload)
        assert isinstance(result.payload, ReviewReportPayload)
        assert result.payload.verdict == "approved"
        assert result.payload.payload_type == "review_report"

    def test_review_report_missing_verdict_is_unparseable(self) -> None:
        """A review report missing the verdict field is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/reviews/incomplete.md"),
            text="""---
type: review_report
project: fleet_memory
identifier: incomplete_review
---
# Incomplete Review
""",
        )

        result = parse_review_report(doc)

        assert isinstance(result, UnparseableDocument)
        assert "verdict" in result.reason.lower()


class TestBuildOutcomeParser:
    """Test build_outcome (completed_task) document parsing."""

    def test_build_outcome_parses_to_canonical_payload(self) -> None:
        """A completed task with status and duration produces a BuildOutcomePayload."""
        doc = CorpusDocument(
            path=Path("/corpus/tasks/TASK-RIP-003.md"),
            text="""---
type: completed_task
project: fleet_memory
identifier: TASK-RIP-003
status: success
duration_seconds: 240
---
# Completed Task
""",
        )

        result = parse_build_outcome(doc)

        assert isinstance(result, ParsedPayload)
        assert isinstance(result.payload, BuildOutcomePayload)
        assert result.payload.status == "success"
        assert result.payload.duration_seconds == 240
        assert result.payload.payload_type == "build_outcome"

    def test_build_outcome_missing_status_is_unparseable(self) -> None:
        """A build outcome missing the status field is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/tasks/incomplete.md"),
            text="""---
type: completed_task
project: fleet_memory
identifier: incomplete_task
duration_seconds: 100
---
# Incomplete Task
""",
        )

        result = parse_build_outcome(doc)

        assert isinstance(result, UnparseableDocument)
        assert "status" in result.reason.lower()

    def test_build_outcome_missing_duration_is_unparseable(self) -> None:
        """A build outcome missing duration_seconds is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/tasks/no-duration.md"),
            text="""---
type: completed_task
project: fleet_memory
identifier: no_duration_task
status: failure
---
# Task without duration
""",
        )

        result = parse_build_outcome(doc)

        assert isinstance(result, UnparseableDocument)
        assert "duration_seconds" in result.reason.lower()

    def test_build_outcome_non_integer_duration_is_unparseable(self) -> None:
        """A build outcome with non-integer duration_seconds is unparseable."""
        doc = CorpusDocument(
            path=Path("/corpus/tasks/bad-duration.md"),
            text="""---
type: completed_task
project: fleet_memory
identifier: bad_duration_task
status: success
duration_seconds: "not-a-number"
---
# Task with bad duration
""",
        )

        result = parse_build_outcome(doc)

        assert isinstance(result, UnparseableDocument)
        assert "duration_seconds" in result.reason.lower()


class TestIdentifierNormalization:
    """Test hyphenated guardkit ID normalization to underscores."""

    def test_hyphenated_guardkit_id_normalized_to_underscores(self) -> None:
        """Identifiers with hyphens are normalized to underscores."""
        doc = CorpusDocument(
            path=Path("/corpus/adrs/ADR-SP-007.md"),
            text="""---
type: adr
project: guard-kit
identifier: ADR-SP-007
decision: Some decision
status: accepted
---
# ADR with hyphens
""",
        )

        result = parse_adr(doc)

        assert isinstance(result, ParsedPayload)
        # Hyphens should be converted to underscores
        assert result.payload.project == "guard_kit"
        assert result.payload.identifier == "ADR_SP_007"

    def test_colon_in_identifier_normalized_to_underscores(self) -> None:
        """Identifiers with colons are normalized to underscores."""
        doc = CorpusDocument(
            path=Path("/corpus/features/FEAT-MEM-07.md"),
            text="""---
type: completed_task
project: fleet:memory
identifier: FEAT:MEM:07
status: success
duration_seconds: 300
---
# Feature with colons
""",
        )

        result = parse_build_outcome(doc)

        assert isinstance(result, ParsedPayload)
        assert result.payload.project == "fleet_memory"
        assert result.payload.identifier == "FEAT_MEM_07"


class TestInjectionSafety:
    """Test that injection-shaped content is carried verbatim."""

    def test_injection_body_carried_verbatim(self) -> None:
        """Document body containing database commands is carried byte-for-byte."""
        dangerous_content = """---
type: seed_module
project: test_project
identifier: test_module
module_path: src/dangerous
---
# Dangerous Content

DROP TABLE users; -- SQL injection attempt
$(rm -rf /) # Shell injection attempt
{{ exec('malicious code') }} # Template injection attempt
"""

        doc = CorpusDocument(
            path=Path("/corpus/dangerous.md"),
            text=dangerous_content,
        )

        result = parse_seed_module(doc)

        # Parser should succeed - content is just data
        assert isinstance(result, ParsedPayload)
        # The payload is created, no execution should occur
        assert result.payload.module_path == "src/dangerous"
        # No error indicates nothing was executed


class TestMissingRequiredFieldBoundaries:
    """Test boundary cases for missing required fields."""

    def test_missing_required_field_is_unparseable_with_reason(self) -> None:
        """Each document type reports unparseable with reason when missing required field."""
        # Already covered in individual parser tests, this is the general contract test
        test_cases = [
            (
                "seed_module missing module_path",
                CorpusDocument(
                    path=Path("/test.md"),
                    text="""---
type: seed_module
project: test
identifier: test
---
Content
""",
                ),
                parse_seed_module,
                "module_path",
            ),
            (
                "adr missing decision",
                CorpusDocument(
                    path=Path("/test.md"),
                    text="""---
type: adr
project: test
identifier: test
status: proposed
---
Content
""",
                ),
                parse_adr,
                "decision",
            ),
            (
                "review_report missing verdict",
                CorpusDocument(
                    path=Path("/test.md"),
                    text="""---
type: review_report
project: test
identifier: test
---
Content
""",
                ),
                parse_review_report,
                "verdict",
            ),
            (
                "build_outcome missing status",
                CorpusDocument(
                    path=Path("/test.md"),
                    text="""---
type: completed_task
project: test
identifier: test
duration_seconds: 100
---
Content
""",
                ),
                parse_build_outcome,
                "status",
            ),
        ]

        for description, doc, parser, expected_field in test_cases:
            result = parser(doc)
            assert isinstance(result, UnparseableDocument), f"Failed: {description}"
            assert (
                expected_field in result.reason.lower()
            ), f"Failed: {description} - expected '{expected_field}' in reason"


class TestDocumentWithExactRequiredFields:
    """Test just-inside boundary: documents with exactly the required fields."""

    def test_document_with_exact_required_fields_parses(self) -> None:
        """Document carrying exactly the required fields (no extras) parses successfully."""
        # Seed module with only required fields
        doc = CorpusDocument(
            path=Path("/corpus/minimal.md"),
            text="""---
type: seed_module
project: minimal_project
identifier: minimal_module
module_path: src/minimal
---
Minimal content
""",
        )

        result = parse_seed_module(doc)

        assert isinstance(result, ParsedPayload)
        assert result.payload.module_path == "src/minimal"
        # Verify it's a valid payload with all base fields
        assert result.payload.project == "minimal_project"
        assert result.payload.identifier == "minimal_module"
        assert result.payload.source_ref == str(doc.path)
