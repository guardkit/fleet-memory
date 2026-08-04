"""Deterministic parser for completed guardkit task files.

Corpus reality replaced the old four-parser dispatch (seed_module / adr /
review_report / build_outcome from front-matter ``type:``) with a single
``parse_completed_task``: the only reindex-owned corpus lane is tasks/completed
and every publishable file there is a completed task.

Identifier contract: BYTE-IDENTICAL to guardkit's ``sanitize_identifier``
semantics — ``re.sub(r"[^A-Za-z0-9_]+", "_", id).strip("_")``. Dots collapse to
underscores (``TASK-CRS-014.7`` -> ``TASK_CRS_014_7``): 38 live ids carry dots,
and the old hyphen/colon-only replacement would have DLQ'd every one of them
(IDENTIFIER_PATTERN rejects dots).

Security: the parser makes no LLM calls and treats document content strictly as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fleet_memory.payloads.base import BasePayload, IdentifierValidationError
from fleet_memory.payloads.models import BuildOutcomePayload
from fleet_memory.reindex.classify import TERMINAL_STATUSES, extract_frontmatter
from fleet_memory.reindex.walker import CorpusDocument

# Headings that open a lessons section: "## Lessons", "## Lessons Learned",
# "### Key Learnings", ... (case-insensitive). Only 73 of 1,545 publishable
# files carry one — absence is normal, never an error.
_LESSONS_HEADING = re.compile(
    r"^(#{2,3})\s+.*(lessons|key learnings).*$",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^(#{1,6})\s+\S")


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


def sanitize_identifier(value: str) -> str:
    """Coerce a guardkit id to fleet-memory's identifier contract ``^[a-zA-Z0-9_]+$``.

    BYTE-IDENTICAL semantics to guardkit's
    ``guardkit.knowledge.fleet_memory_payloads.sanitize_identifier`` — one rule
    mints the identifier on both sides so writes, reads and audits agree on the
    same natural key (``TASK-CRS-014.7`` -> ``TASK_CRS_014_7`` -> natural_key
    ``build_outcome:guardkit:TASK_CRS_014_7``).

    Args:
        value: Raw id from document front-matter

    Returns:
        Sanitized identifier ("unknown" for empty/all-punctuation input)
    """
    if not value:
        return "unknown"
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return cleaned or "unknown"


def extract_lessons(text: str) -> str | None:
    """Extract the "## Lessons"/"Key Learnings" section body, if present.

    Captures from the matching heading to the next heading of the same or
    higher level (or end of document). Deeper sub-headings stay inside the
    section — live lessons sections carry "### What Went Well" style
    subsections under a "## Lessons Learned" heading.

    Args:
        text: Raw markdown document text

    Returns:
        Stripped section body, or None when no lessons section exists
    """
    lines = text.splitlines()
    start: int | None = None
    lessons_level = 0

    for index, line in enumerate(lines):
        match = _LESSONS_HEADING.match(line)
        if match:
            start = index + 1
            lessons_level = len(match.group(1))
            break

    if start is None:
        return None

    body_lines: list[str] = []
    for line in lines[start:]:
        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) <= lessons_level:
            break
        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return body or None


def _normalize_tags(raw_tags: Any) -> list[str]:
    """Coerce a front-matter tags value to a list of strings."""
    if isinstance(raw_tags, list):
        return [str(tag) for tag in raw_tags]
    if isinstance(raw_tags, str) and raw_tags.strip():
        return [raw_tags.strip()]
    return []


def parse_completed_task(
    doc: CorpusDocument,
    corpus_root: Path,
    frontmatter: dict[str, Any] | None = None,
) -> ParsedPayload | UnparseableDocument:
    """Parse a completed task document into a BuildOutcomePayload.

    Field mapping (corpus reality -> store vocabulary):
    - identifier/task_id: sanitized front-matter id (dots collapse to underscores)
    - status: ALL terminal file statuses map to "success" — the store's existing
      vocabulary from the runtime lane; two vocabularies in one payload type is
      noise. The original file status is carried as domain tag "fm-status:<s>".
    - duration_seconds: 0 (task files carry no build duration)
    - lessons: extracted "## Lessons"/"Key Learnings" section, else None
    - domain_tags: front-matter tags + ["task", "fm-status:<s>"]
    - source_ref: repo-relative path; project: literal "guardkit"

    Args:
        doc: Corpus document to parse (classified publishable)
        corpus_root: Repository checkout root (for the repo-relative source_ref)
        frontmatter: Already-parsed front-matter from classification (optional;
            re-extracted when not provided)

    Returns:
        ParsedPayload with BuildOutcomePayload, or UnparseableDocument with reason
    """
    if frontmatter is None:
        try:
            frontmatter = extract_frontmatter(doc.text)
        except yaml.YAMLError as e:
            return UnparseableDocument(
                reason=f"Failed to parse YAML front-matter: {e}",
                document_path=doc.path,
            )

    if not isinstance(frontmatter, dict):
        return UnparseableDocument(
            reason="No YAML front-matter found",
            document_path=doc.path,
        )

    raw_id = frontmatter.get("id")
    if not raw_id:
        return UnparseableDocument(
            reason="Missing required field: id",
            document_path=doc.path,
        )

    raw_status = str(frontmatter.get("status", "")).strip()
    if raw_status.lower() not in TERMINAL_STATUSES:
        return UnparseableDocument(
            reason=f"Non-terminal status: {raw_status or '(missing)'}",
            document_path=doc.path,
        )

    identifier = sanitize_identifier(str(raw_id))

    try:
        relative = doc.path.resolve().relative_to(corpus_root.resolve())
        source_ref = str(relative).replace("\\", "/")
    except ValueError:
        return UnparseableDocument(
            reason=f"Document path escapes corpus root: {doc.path}",
            document_path=doc.path,
        )

    domain_tags = _normalize_tags(frontmatter.get("tags"))
    domain_tags.extend(["task", f"fm-status:{raw_status}"])

    try:
        payload = BuildOutcomePayload(
            project="guardkit",  # Literal - no hyphens (DLQ poison)
            identifier=identifier,
            status="success",
            duration_seconds=0,
            task_id=identifier,
            lessons=extract_lessons(doc.text),
            domain_tags=domain_tags,
            source_ref=source_ref,
        )
    except IdentifierValidationError as e:
        return UnparseableDocument(
            reason=f"Identifier validation failed: {e}",
            document_path=doc.path,
        )

    return ParsedPayload(payload=payload, document_path=doc.path)
