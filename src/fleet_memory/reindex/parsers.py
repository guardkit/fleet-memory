"""Deterministic typed parsers for fleet-memory corpus documents.

Each parser produces a canonical typed payload from a classified document,
extracting natural-key segments (project, identifier) and required type-specific
fields. Guardkit IDs with hyphens/colons are normalized to underscores to satisfy
IDENTIFIER_PATTERN (^[a-zA-Z0-9_]+$).

Security: parsers make no LLM calls and treat document content strictly as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fleet_memory.payloads.base import BasePayload, IdentifierValidationError
from fleet_memory.payloads.models import (
    ADRPayload,
    BuildOutcomePayload,
    ReviewReportPayload,
    SeedModulePayload,
)
from fleet_memory.reindex.walker import CorpusDocument


@dataclass(frozen=True)
class ParsedPayload:
    """Successfully parsed document with canonical typed payload.

    Attributes:
        payload: The concrete BasePayload subclass instance
        document_path: Source document path for accounting
    """

    payload: BasePayload
    document_path: Path


@dataclass(frozen=True)
class UnparseableDocument:
    """Document that could not be parsed into a payload.

    Attributes:
        reason: Human-readable explanation of why parsing failed
        document_path: Source document path for accounting
    """

    reason: str
    document_path: Path


def _normalize_identifier(raw_value: str) -> str:
    """Normalize guardkit identifiers to satisfy IDENTIFIER_PATTERN.

    Converts hyphens and colons to underscores.

    Args:
        raw_value: Raw identifier from document front-matter

    Returns:
        Normalized identifier matching ^[a-zA-Z0-9_]+$
    """
    # Replace hyphens and colons with underscores
    normalized = raw_value.replace("-", "_").replace(":", "_")
    return normalized


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
    return yaml.safe_load(yaml_content)


def parse_seed_module(doc: CorpusDocument) -> ParsedPayload | UnparseableDocument:
    """Parse a seed_module document into a SeedModulePayload.

    Required fields:
        - project: Project identifier
        - identifier: Module identifier
        - module_path: Path to the seed module

    Args:
        doc: Corpus document to parse

    Returns:
        ParsedPayload with SeedModulePayload, or UnparseableDocument with reason
    """
    try:
        frontmatter = _extract_frontmatter(doc.text)
    except yaml.YAMLError as e:
        return UnparseableDocument(
            reason=f"Failed to parse YAML front-matter: {str(e)}",
            document_path=doc.path,
        )

    if frontmatter is None:
        return UnparseableDocument(
            reason="No YAML front-matter found",
            document_path=doc.path,
        )

    # Extract and validate required fields
    project = frontmatter.get("project")
    identifier = frontmatter.get("identifier")
    module_path = frontmatter.get("module_path")

    if not project:
        return UnparseableDocument(
            reason="Missing required field: project",
            document_path=doc.path,
        )

    if not identifier:
        return UnparseableDocument(
            reason="Missing required field: identifier",
            document_path=doc.path,
        )

    if not module_path:
        return UnparseableDocument(
            reason="Missing required field: module_path",
            document_path=doc.path,
        )

    # Normalize identifiers
    normalized_project = _normalize_identifier(project)
    normalized_identifier = _normalize_identifier(identifier)

    # Construct payload
    try:
        payload = SeedModulePayload(
            project=normalized_project,
            identifier=normalized_identifier,
            module_path=module_path,
            source_ref=str(doc.path),
        )
    except IdentifierValidationError as e:
        return UnparseableDocument(
            reason=f"Identifier validation failed: {str(e)}",
            document_path=doc.path,
        )

    return ParsedPayload(
        payload=payload,
        document_path=doc.path,
    )


def parse_adr(doc: CorpusDocument) -> ParsedPayload | UnparseableDocument:
    """Parse an ADR document into an ADRPayload.

    Required fields:
        - project: Project identifier
        - identifier: ADR identifier
        - decision: The architectural decision text
        - status: Decision status (e.g., "proposed", "accepted")

    Args:
        doc: Corpus document to parse

    Returns:
        ParsedPayload with ADRPayload, or UnparseableDocument with reason
    """
    try:
        frontmatter = _extract_frontmatter(doc.text)
    except yaml.YAMLError as e:
        return UnparseableDocument(
            reason=f"Failed to parse YAML front-matter: {str(e)}",
            document_path=doc.path,
        )

    if frontmatter is None:
        return UnparseableDocument(
            reason="No YAML front-matter found",
            document_path=doc.path,
        )

    # Extract and validate required fields
    project = frontmatter.get("project")
    identifier = frontmatter.get("identifier")
    decision = frontmatter.get("decision")
    status = frontmatter.get("status")

    if not project:
        return UnparseableDocument(
            reason="Missing required field: project",
            document_path=doc.path,
        )

    if not identifier:
        return UnparseableDocument(
            reason="Missing required field: identifier",
            document_path=doc.path,
        )

    if not decision:
        return UnparseableDocument(
            reason="Missing required field: decision",
            document_path=doc.path,
        )

    if not status:
        return UnparseableDocument(
            reason="Missing required field: status",
            document_path=doc.path,
        )

    # Normalize identifiers
    normalized_project = _normalize_identifier(project)
    normalized_identifier = _normalize_identifier(identifier)

    # Construct payload
    try:
        payload = ADRPayload(
            project=normalized_project,
            identifier=normalized_identifier,
            decision=decision,
            status=status,
            source_ref=str(doc.path),
        )
    except IdentifierValidationError as e:
        return UnparseableDocument(
            reason=f"Identifier validation failed: {str(e)}",
            document_path=doc.path,
        )

    return ParsedPayload(
        payload=payload,
        document_path=doc.path,
    )


def parse_review_report(doc: CorpusDocument) -> ParsedPayload | UnparseableDocument:
    """Parse a review_report document into a ReviewReportPayload.

    Required fields:
        - project: Project identifier
        - identifier: Review report identifier
        - verdict: Review verdict (e.g., "approved", "rejected")

    Args:
        doc: Corpus document to parse

    Returns:
        ParsedPayload with ReviewReportPayload, or UnparseableDocument with reason
    """
    try:
        frontmatter = _extract_frontmatter(doc.text)
    except yaml.YAMLError as e:
        return UnparseableDocument(
            reason=f"Failed to parse YAML front-matter: {str(e)}",
            document_path=doc.path,
        )

    if frontmatter is None:
        return UnparseableDocument(
            reason="No YAML front-matter found",
            document_path=doc.path,
        )

    # Extract and validate required fields
    project = frontmatter.get("project")
    identifier = frontmatter.get("identifier")
    verdict = frontmatter.get("verdict")

    if not project:
        return UnparseableDocument(
            reason="Missing required field: project",
            document_path=doc.path,
        )

    if not identifier:
        return UnparseableDocument(
            reason="Missing required field: identifier",
            document_path=doc.path,
        )

    if not verdict:
        return UnparseableDocument(
            reason="Missing required field: verdict",
            document_path=doc.path,
        )

    # Normalize identifiers
    normalized_project = _normalize_identifier(project)
    normalized_identifier = _normalize_identifier(identifier)

    # Construct payload
    try:
        payload = ReviewReportPayload(
            project=normalized_project,
            identifier=normalized_identifier,
            verdict=verdict,
            source_ref=str(doc.path),
        )
    except IdentifierValidationError as e:
        return UnparseableDocument(
            reason=f"Identifier validation failed: {str(e)}",
            document_path=doc.path,
        )

    return ParsedPayload(
        payload=payload,
        document_path=doc.path,
    )


def parse_build_outcome(doc: CorpusDocument) -> ParsedPayload | UnparseableDocument:
    """Parse a completed_task document into a BuildOutcomePayload.

    Required fields:
        - project: Project identifier
        - identifier: Task identifier
        - status: Build status (e.g., "success", "failure")
        - duration_seconds: Build duration as integer

    Args:
        doc: Corpus document to parse

    Returns:
        ParsedPayload with BuildOutcomePayload, or UnparseableDocument with reason
    """
    try:
        frontmatter = _extract_frontmatter(doc.text)
    except yaml.YAMLError as e:
        return UnparseableDocument(
            reason=f"Failed to parse YAML front-matter: {str(e)}",
            document_path=doc.path,
        )

    if frontmatter is None:
        return UnparseableDocument(
            reason="No YAML front-matter found",
            document_path=doc.path,
        )

    # Extract and validate required fields
    project = frontmatter.get("project")
    identifier = frontmatter.get("identifier")
    status = frontmatter.get("status")
    duration_seconds = frontmatter.get("duration_seconds")

    if not project:
        return UnparseableDocument(
            reason="Missing required field: project",
            document_path=doc.path,
        )

    if not identifier:
        return UnparseableDocument(
            reason="Missing required field: identifier",
            document_path=doc.path,
        )

    if not status:
        return UnparseableDocument(
            reason="Missing required field: status",
            document_path=doc.path,
        )

    if duration_seconds is None:
        return UnparseableDocument(
            reason="Missing required field: duration_seconds",
            document_path=doc.path,
        )

    # Validate duration_seconds is an integer
    if not isinstance(duration_seconds, int):
        return UnparseableDocument(
            reason="Field duration_seconds must be an integer",
            document_path=doc.path,
        )

    # Normalize identifiers
    normalized_project = _normalize_identifier(project)
    normalized_identifier = _normalize_identifier(identifier)

    # Construct payload
    try:
        payload = BuildOutcomePayload(
            project=normalized_project,
            identifier=normalized_identifier,
            status=status,
            duration_seconds=duration_seconds,
            source_ref=str(doc.path),
        )
    except IdentifierValidationError as e:
        return UnparseableDocument(
            reason=f"Identifier validation failed: {str(e)}",
            document_path=doc.path,
        )

    return ParsedPayload(
        payload=payload,
        document_path=doc.path,
    )
