"""Unit tests for document classification and parser dispatch.

Tests front-matter parsing, document kind classification, and dispatch logic.
"""

from __future__ import annotations

from pathlib import Path

from fleet_memory.reindex.classify import (
    DocumentKind,
    classify_document,
    get_parser_dispatch_table,
)
from fleet_memory.reindex.walker import CorpusDocument


def test_malformed_frontmatter_reports_reason() -> None:
    """A document with malformed YAML front-matter yields parse_failure with reason.

    The parser must not raise an exception - it returns a structured result
    carrying the source reference and a human-readable reason.
    """
    # Arrange - document with invalid YAML front-matter
    doc = CorpusDocument(
        path=Path("/corpus/broken.md"),
        text="""---
invalid: yaml: content: [
no: closing: bracket
---

# Content
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "parse_failure"
    assert result.document_path == Path("/corpus/broken.md")
    assert result.reason is not None
    assert len(result.reason) > 0
    # Should mention YAML or parsing in the reason
    assert any(keyword in result.reason.lower() for keyword in ["yaml", "parse", "front"])


def test_unrecognized_kind_reported() -> None:
    """A document matching no known parser yields unrecognized with reason."""
    # Arrange - valid YAML but unrecognized document kind
    doc = CorpusDocument(
        path=Path("/corpus/unknown.md"),
        text="""---
title: Some Document
type: unknown_document_type
---

# Content
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "unrecognized"
    assert result.document_path == Path("/corpus/unknown.md")
    assert result.reason is not None
    assert len(result.reason) > 0


def test_each_known_kind_dispatches_to_a_parser() -> None:
    """Each of the four known document kinds maps to a parser callable.

    The dispatch table must contain entries for:
    - seed_module
    - adr
    - review_report
    - completed_task
    """
    # Act
    dispatch_table = get_parser_dispatch_table()

    # Assert
    assert DocumentKind.SEED_MODULE in dispatch_table
    assert DocumentKind.ADR in dispatch_table
    assert DocumentKind.REVIEW_REPORT in dispatch_table
    assert DocumentKind.COMPLETED_TASK in dispatch_table

    # Each entry should be callable
    for kind, parser in dispatch_table.items():
        assert callable(parser), f"{kind} parser is not callable"


def test_missing_frontmatter_yields_unrecognized() -> None:
    """A document with no front-matter block is treated as unrecognized, not crash."""
    # Arrange - document with no front-matter
    doc = CorpusDocument(
        path=Path("/corpus/no_fm.md"),
        text="""# Just a heading

Some content without front-matter.
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "unrecognized"
    assert result.document_path == Path("/corpus/no_fm.md")
    assert result.reason is not None


def test_seed_module_recognized() -> None:
    """A seed module document is correctly classified."""
    # Arrange - document that looks like a seed module
    doc = CorpusDocument(
        path=Path("/corpus/modules/auth.md"),
        text="""---
module_id: auth
type: seed_module
title: Authentication Module
---

# Auth Module
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "parsed"
    assert result.kind == DocumentKind.SEED_MODULE
    assert result.document_path == Path("/corpus/modules/auth.md")


def test_adr_recognized() -> None:
    """An ADR document is correctly classified."""
    # Arrange - document that looks like an ADR
    doc = CorpusDocument(
        path=Path("/corpus/decisions/adr-001.md"),
        text="""---
id: ADR-001
type: adr
title: Use PostgreSQL for persistence
status: accepted
---

# ADR-001
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "parsed"
    assert result.kind == DocumentKind.ADR
    assert result.document_path == Path("/corpus/decisions/adr-001.md")


def test_review_report_recognized() -> None:
    """A review report document is correctly classified."""
    # Arrange
    doc = CorpusDocument(
        path=Path("/corpus/reviews/review-001.md"),
        text="""---
review_id: REV-001
type: review_report
title: Code Review Report
---

# Review Report
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "parsed"
    assert result.kind == DocumentKind.REVIEW_REPORT
    assert result.document_path == Path("/corpus/reviews/review-001.md")


def test_completed_task_recognized() -> None:
    """A completed task document is correctly classified."""
    # Arrange
    doc = CorpusDocument(
        path=Path("/corpus/tasks/completed/TASK-001.md"),
        text="""---
id: TASK-001
type: completed_task
title: Implement feature X
status: completed
---

# Task Report
""",
    )

    # Act
    result = classify_document(doc)

    # Assert
    assert result.status == "parsed"
    assert result.kind == DocumentKind.COMPLETED_TASK
    assert result.document_path == Path("/corpus/tasks/completed/TASK-001.md")
