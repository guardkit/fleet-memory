"""Document classification and parser dispatch for fleet-memory reindexing.

Reads YAML front-matter from corpus documents and classifies their document kind
deterministically from path conventions and front-matter fields. Dispatches to
the appropriate parser based on kind.

Security property: malformed front-matter and unrecognized kinds are reported
with reasons, never guessed at and never silently dropped (ASSUM-004).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from fleet_memory.reindex.walker import CorpusDocument


class DocumentKind(str, Enum):
    """Known document kinds in the corpus.

    Each kind maps to a specific parser in the dispatch table.
    """

    SEED_MODULE = "seed_module"
    ADR = "adr"
    REVIEW_REPORT = "review_report"
    COMPLETED_TASK = "completed_task"


@dataclass(frozen=True)
class ParseResult:
    """Result of document classification and parsing.

    A tagged union representing one of three outcomes:
    - parsed: Successfully classified with a known kind
    - parse_failure: Front-matter could not be parsed
    - unrecognized: Valid front-matter but unknown kind

    Attributes:
        status: One of "parsed", "parse_failure", or "unrecognized"
        document_path: Source document path for accounting
        kind: Document kind (only set when status == "parsed")
        reason: Human-readable explanation (set for parse_failure and unrecognized)
    """

    status: str  # "parsed" | "parse_failure" | "unrecognized"
    document_path: Path
    kind: DocumentKind | None = None
    reason: str | None = None


def _extract_frontmatter(text: str) -> dict[str, Any] | None:
    """Extract and parse YAML front-matter from markdown text.

    Args:
        text: Raw markdown document text

    Returns:
        Parsed front-matter dict, or None if no front-matter found

    Raises:
        yaml.YAMLError: If front-matter exists but is malformed
    """
    # Match YAML front-matter block: --- ... ---
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, text, re.DOTALL)

    if not match:
        return None

    yaml_content = match.group(1)
    # This may raise yaml.YAMLError if malformed
    return yaml.safe_load(yaml_content)


def _classify_kind(frontmatter: dict[str, Any], path: Path) -> DocumentKind | None:
    """Classify document kind from front-matter fields.

    Classification is deterministic based on the 'type' field in front-matter.

    Args:
        frontmatter: Parsed front-matter dictionary
        path: Document path (for path-based heuristics if needed)

    Returns:
        Classified DocumentKind, or None if unrecognized
    """
    doc_type = frontmatter.get("type", "").lower()

    # Map type field to DocumentKind
    type_mapping = {
        "seed_module": DocumentKind.SEED_MODULE,
        "adr": DocumentKind.ADR,
        "review_report": DocumentKind.REVIEW_REPORT,
        "completed_task": DocumentKind.COMPLETED_TASK,
    }

    return type_mapping.get(doc_type)


def classify_document(doc: CorpusDocument) -> ParseResult:
    """Classify a corpus document by reading its front-matter.

    Returns a structured result for every document:
    - Malformed front-matter → parse_failure with reason
    - Missing/unrecognized kind → unrecognized with reason
    - Known kind → parsed with kind

    Args:
        doc: Corpus document to classify

    Returns:
        ParseResult with classification outcome
    """
    # Try to extract front-matter
    try:
        frontmatter = _extract_frontmatter(doc.text)
    except yaml.YAMLError as e:
        # Malformed YAML in front-matter
        return ParseResult(
            status="parse_failure",
            document_path=doc.path,
            reason=f"Failed to parse YAML front-matter: {str(e)}",
        )

    # No front-matter found
    if frontmatter is None:
        return ParseResult(
            status="unrecognized",
            document_path=doc.path,
            reason="No YAML front-matter block found",
        )

    # Classify the document kind
    kind = _classify_kind(frontmatter, doc.path)

    if kind is None:
        # Valid front-matter but unrecognized type
        doc_type = frontmatter.get("type", "(missing)")
        return ParseResult(
            status="unrecognized",
            document_path=doc.path,
            reason=f"Unrecognized document type: {doc_type}",
        )

    # Successfully classified
    return ParseResult(
        status="parsed",
        document_path=doc.path,
        kind=kind,
    )


# Placeholder parser callables (actual parsers land in TASK-RIP-004)
def _parse_seed_module(doc: CorpusDocument) -> dict[str, Any]:
    """Placeholder parser for seed module documents."""
    return {"kind": "seed_module", "path": str(doc.path)}


def _parse_adr(doc: CorpusDocument) -> dict[str, Any]:
    """Placeholder parser for ADR documents."""
    return {"kind": "adr", "path": str(doc.path)}


def _parse_review_report(doc: CorpusDocument) -> dict[str, Any]:
    """Placeholder parser for review report documents."""
    return {"kind": "review_report", "path": str(doc.path)}


def _parse_completed_task(doc: CorpusDocument) -> dict[str, Any]:
    """Placeholder parser for completed task documents."""
    return {"kind": "completed_task", "path": str(doc.path)}


def get_parser_dispatch_table() -> dict[DocumentKind, Callable[[CorpusDocument], Any]]:
    """Get the dispatch table mapping document kinds to parser callables.

    The parsers themselves are implemented in TASK-RIP-004. This task
    establishes the dispatch mechanism.

    Returns:
        Dictionary mapping each DocumentKind to its parser function
    """
    return {
        DocumentKind.SEED_MODULE: _parse_seed_module,
        DocumentKind.ADR: _parse_adr,
        DocumentKind.REVIEW_REPORT: _parse_review_report,
        DocumentKind.COMPLETED_TASK: _parse_completed_task,
    }
