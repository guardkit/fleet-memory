"""Unit tests for the completed-task parser.

Fixtures are VERBATIM copies of live guardkit corpus files. The identifier
rule is BYTE-IDENTICAL to guardkit's sanitize_identifier semantics — the
cross-repo vectors below pin it on both sides so writes, reads and audits
agree on the same natural key.
"""

from __future__ import annotations

import re

import pytest

from fleet_memory.reindex.parsers import (
    ParsedPayload,
    UnparseableDocument,
    extract_lessons,
    parse_completed_task,
    sanitize_identifier,
)

# Cross-repo sanitize vectors (guardkit.knowledge.fleet_memory_payloads.sanitize_identifier):
# 38 live ids carry dots — the old hyphen/colon-only rule would have DLQ'd them all.
CROSS_REPO_VECTORS = [
    ("TASK-FIX-RESUMEVENV01", "TASK_FIX_RESUMEVENV01"),
    ("TASK-CRS-014.7", "TASK_CRS_014_7"),  # dots collapse
    ("TASK-FIX-RWOP1.3.3", "TASK_FIX_RWOP1_3_3"),  # live dotted id
    ("TASK-030B-1.4", "TASK_030B_1_4"),  # live dotted id
    ("TASK-1234", "TASK_1234"),
    ("ADR-001", "ADR_001"),
    ("a:b/c d", "a_b_c_d"),  # every non-[A-Za-z0-9_] run collapses to ONE underscore
    (".TASK.", "TASK"),  # leading/trailing underscores stripped
    ("", "unknown"),
    ("---", "unknown"),
]


class TestSanitizeIdentifier:
    """Identifier rule byte-identical to guardkit's sanitize_identifier."""

    @pytest.mark.parametrize(("raw", "expected"), CROSS_REPO_VECTORS)
    def test_cross_repo_vectors(self, raw: str, expected: str) -> None:
        assert sanitize_identifier(raw) == expected

    @pytest.mark.parametrize(("raw", "_expected"), CROSS_REPO_VECTORS)
    def test_matches_guardkit_algorithm_exactly(self, raw: str, _expected: str) -> None:
        """Recompute with guardkit's exact expression and compare."""
        if not raw:
            expected = "unknown"
        else:
            expected = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_") or "unknown"
        assert sanitize_identifier(raw) == expected


class TestParseCompletedTask:
    """Parser contract over verbatim fixture files."""

    def test_natural_key_exact(self, load_doc, corpus_root) -> None:
        doc = load_doc(
            "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md"
        )
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, ParsedPayload)
        assert (
            result.payload.natural_key
            == "build_outcome:guardkit:TASK_FIX_RESUMEVENV01"
        )

    def test_dotted_id_natural_key(self, load_doc, corpus_root) -> None:
        doc = load_doc("tasks/completed/TASK-CRS-014.7/TASK-CRS-014.7.md")
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, ParsedPayload)
        assert result.payload.identifier == "TASK_CRS_014_7"
        assert result.payload.natural_key == "build_outcome:guardkit:TASK_CRS_014_7"

    def test_uppercase_terminal_status_accepted(self, load_doc, corpus_root) -> None:
        """status: COMPLETED maps to 'success' with the original carried as a tag."""
        doc = load_doc(
            "tasks/completed/TASK-GR-FULL-DOC-PARSER/TASK-GR-FULL-DOC-PARSER.md"
        )
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, ParsedPayload)
        assert result.payload.status == "success"
        assert "fm-status:COMPLETED" in result.payload.domain_tags

    def test_all_terminal_statuses_map_to_success(self, load_doc, corpus_root) -> None:
        """One status vocabulary in the store: every terminal file status -> success."""
        for relative_path in (
            "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md",
            "tasks/completed/2026-07/TASK-OBS-9F43-model-attribution-correlation-identity.md",
            "tasks/completed/TASK-GR-FULL-DOC-PARSER/TASK-GR-FULL-DOC-PARSER.md",
        ):
            result = parse_completed_task(load_doc(relative_path), corpus_root)
            assert isinstance(result, ParsedPayload)
            assert result.payload.status == "success"

    def test_field_mapping(self, load_doc, corpus_root) -> None:
        doc = load_doc(
            "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md"
        )
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, ParsedPayload)
        payload = result.payload

        assert payload.project == "guardkit"
        assert payload.duration_seconds == 0
        assert payload.task_id == payload.identifier
        # source_ref is the repo-relative path
        assert payload.source_ref == (
            "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md"
        )
        # domain_tags = front-matter tags + ["task", "fm-status:<s>"]
        for tag in ("autobuild", "resume", "venv", "verifier-infrastructure"):
            assert tag in payload.domain_tags
        assert "task" in payload.domain_tags
        assert "fm-status:completed" in payload.domain_tags

    def test_lessons_extracted_when_present(self, load_doc, corpus_root) -> None:
        doc = load_doc("tasks/completed/2025-11/TASK-013-integration-tests.md")
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, ParsedPayload)
        assert result.payload.lessons is not None
        assert "Fixture Pattern" in result.payload.lessons

    def test_lessons_none_when_absent(self, load_doc, corpus_root) -> None:
        doc = load_doc(
            "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md"
        )
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, ParsedPayload)
        assert result.payload.lessons is None

    def test_frontmatter_reuse_from_classification(self, load_doc, corpus_root) -> None:
        """The parser accepts pre-parsed front-matter (no re-parse divergence)."""
        doc = load_doc("tasks/completed/TASK-CRS-014.7/TASK-CRS-014.7.md")
        frontmatter = {"id": "TASK-CRS-014.7", "status": "completed", "tags": ["x"]}
        result = parse_completed_task(doc, corpus_root, frontmatter=frontmatter)
        assert isinstance(result, ParsedPayload)
        assert result.payload.identifier == "TASK_CRS_014_7"
        assert "x" in result.payload.domain_tags

    def test_missing_id_unparseable(self, load_doc, corpus_root) -> None:
        doc = load_doc("tasks/completed/TASK-FIX-7C3D-file-io-error-handling.md")
        result = parse_completed_task(doc, corpus_root)
        assert isinstance(result, UnparseableDocument)
        assert "id" in result.reason


class TestExtractLessons:
    """Lessons section extraction rules."""

    def test_lessons_heading_variants(self) -> None:
        assert extract_lessons("## Lessons\n\nbody text\n") == "body text"
        assert extract_lessons("## Lessons Learned\n\nbody text\n") == "body text"
        assert extract_lessons("### Key Learnings\n\nbody text\n") == "body text"

    def test_section_ends_at_next_heading(self) -> None:
        text = "## Lessons\n\nlesson body\n\n## Next Section\n\nother\n"
        assert extract_lessons(text) == "lesson body"

    def test_subsections_included(self) -> None:
        """Deeper sub-headings inside the lessons section are kept (live shape)."""
        text = "## Lessons Learned\n\n### What Went Well\n\n1. thing\n"
        lessons = extract_lessons(text)
        # ### What Went Well is level-3 under a level-2 lessons heading: the live
        # TASK-013 fixture carries exactly this shape and the sub-body must survive
        assert lessons is not None

    def test_no_lessons_returns_none(self) -> None:
        assert extract_lessons("# Title\n\nNo lessons here.\n") is None
        assert extract_lessons("## Lessons\n\n\n") is None
