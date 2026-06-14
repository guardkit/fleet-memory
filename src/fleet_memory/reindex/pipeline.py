"""Re-index orchestrator coordinating corpus walking, parsing, and publishing.

The orchestrator walks a corpus, classifies each document, parses recognized ones,
and publishes typed episodes. A RunReport accounts for every walked document under
one of three dispositions: published, unparseable, or unrecognized.

Security: one bad document never aborts the full run. Empty corpus completes cleanly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fleet_memory.payloads.base import BasePayload
from fleet_memory.reindex.classify import DocumentKind, classify_document
from fleet_memory.reindex.parsers import (
    ParsedPayload,
    UnparseableDocument,
    parse_adr,
    parse_build_outcome,
    parse_review_report,
    parse_seed_module,
)
from fleet_memory.reindex.walker import CorpusDocument, walk_corpus


@dataclass(frozen=True)
class RunReport:
    """Accounting report for a full corpus reindex run.

    Every walked document appears in exactly one category: published, unparseable,
    or unrecognized. The sum of counts equals total documents walked.

    Attributes:
        published_count: Number of successfully published episodes
        unparseable_count: Number of documents that failed parsing
        unrecognized_count: Number of documents with unrecognized kinds
        unparseable: List of unparseable documents with reasons
        unrecognized: List of unrecognized documents with reasons
    """

    published_count: int = 0
    unparseable_count: int = 0
    unrecognized_count: int = 0
    unparseable: list[dict[str, Any]] = field(default_factory=list)
    unrecognized: list[dict[str, Any]] = field(default_factory=list)


def _get_parser_for_kind(
    kind: DocumentKind,
) -> Callable[[CorpusDocument], ParsedPayload | UnparseableDocument]:
    """Get the appropriate parser function for a document kind.

    Args:
        kind: The classified document kind

    Returns:
        Parser function that takes a CorpusDocument and returns parsed result

    Raises:
        ValueError: If kind has no associated parser
    """
    parser_dispatch = {
        DocumentKind.SEED_MODULE: parse_seed_module,
        DocumentKind.ADR: parse_adr,
        DocumentKind.REVIEW_REPORT: parse_review_report,
        DocumentKind.COMPLETED_TASK: parse_build_outcome,
    }

    parser = parser_dispatch.get(kind)
    if parser is None:
        raise ValueError(f"No parser registered for kind: {kind}")

    return parser


async def reindex_corpus(
    corpus_root: Path,
    publisher: Callable[[BasePayload], Any],
) -> RunReport:
    """Orchestrate full corpus reindex: walk → classify → parse → publish.

    Processes every document in the corpus, publishing typed episodes for recognized
    documents. One bad document never aborts the run. Returns a RunReport accounting
    for every walked document.

    Args:
        corpus_root: Root directory of the corpus to reindex
        publisher: Async callable that publishes a BasePayload (injected for testing)

    Returns:
        RunReport with counts and details for all processed documents
    """
    published_count = 0
    unparseable_list: list[dict[str, Any]] = []
    unrecognized_list: list[dict[str, Any]] = []

    # Walk the corpus and process each document
    for doc in walk_corpus(corpus_root):
        # Classify the document
        classification = classify_document(doc)

        if classification.status == "parsed" and classification.kind is not None:
            # Document is recognized - parse it
            try:
                parser = _get_parser_for_kind(classification.kind)
                parse_result = parser(doc)

                if isinstance(parse_result, ParsedPayload):
                    # Successfully parsed - publish the episode
                    await publisher(parse_result.payload)
                    published_count += 1
                elif isinstance(parse_result, UnparseableDocument):
                    # Parsing failed - record reason
                    unparseable_list.append(
                        {
                            "path": str(parse_result.document_path),
                            "reason": parse_result.reason,
                        }
                    )
                else:
                    # Unexpected result type
                    unparseable_list.append(
                        {
                            "path": str(doc.path),
                            "reason": f"Unexpected parse result type: {type(parse_result)}",
                        }
                    )
            except Exception as e:
                # Parser raised an exception - don't abort the run
                unparseable_list.append(
                    {
                        "path": str(doc.path),
                        "reason": f"Parser error: {str(e)}",
                    }
                )

        elif classification.status == "parse_failure":
            # Document has malformed front-matter
            unparseable_list.append(
                {
                    "path": str(classification.document_path),
                    "reason": classification.reason or "Parse failure",
                }
            )

        elif classification.status == "unrecognized":
            # Document kind is not recognized
            unrecognized_list.append(
                {
                    "path": str(classification.document_path),
                    "reason": classification.reason or "Unrecognized document kind",
                }
            )

        else:
            # Unknown classification status
            unparseable_list.append(
                {
                    "path": str(doc.path),
                    "reason": f"Unknown classification status: {classification.status}",
                }
            )

    # Build the final report
    return RunReport(
        published_count=published_count,
        unparseable_count=len(unparseable_list),
        unrecognized_count=len(unrecognized_list),
        unparseable=unparseable_list,
        unrecognized=unrecognized_list,
    )
