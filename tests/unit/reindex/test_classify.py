"""Unit tests for corpus-reality classification.

Every fixture is a VERBATIM copy of a live guardkit corpus file (see
tests/fixtures/corpus/). The fixture table below is the corpus-reality
contract: real file shapes -> named outcomes. The old front-matter ``type:``
contract classified all of them "unrecognized" — that fiction is what this
lane exists to bank against.
"""

from __future__ import annotations

import pytest

from fleet_memory.reindex.classify import classify_document

# Fixture table: (repo-relative path, expected kind or None, expected skip reason or None)
FIXTURE_TABLE = [
    # Plain completed task — publishable
    (
        "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md",
        "build_outcome",
        None,
    ),
    # Autobuild-block front-matter shape — publishable
    (
        "tasks/completed/2026-07/TASK-OBS-9F43-model-attribution-correlation-identity.md",
        "build_outcome",
        None,
    ),
    # status: COMPLETED uppercase — accepted (case-insensitive terminal)
    (
        "tasks/completed/TASK-GR-FULL-DOC-PARSER/TASK-GR-FULL-DOC-PARSER.md",
        "build_outcome",
        None,
    ),
    # Dotted id — publishable (identifier sanitized downstream)
    (
        "tasks/completed/TASK-CRS-014.7/TASK-CRS-014.7.md",
        "build_outcome",
        None,
    ),
    # Lessons-bearing completed task — publishable
    (
        "tasks/completed/2025-11/TASK-013-integration-tests.md",
        "build_outcome",
        None,
    ),
    # Backlog-status file archived under tasks/completed — named skip
    (
        "tasks/completed/TASK-09E9-comprehensive-template-create-review.md",
        None,
        "non-terminal status: backlog",
    ),
    # Agent definition (name/model/tools keys) living under tasks/completed
    (
        "tasks/completed/agent-enhancement-implementation/agents/python/python-api-specialist.md",
        None,
        "agent-definition shape (name/model/tools keys)",
    ),
    # Completion report with no front-matter block at all
    (
        "tasks/completed/TASK-066-COMPLETION-REPORT.md",
        None,
        "no front-matter",
    ),
    # Front-matter carries task_id but NOT id (live uppercase-status shape)
    (
        "tasks/completed/TASK-FIX-7C3D-file-io-error-handling.md",
        None,
        "front-matter without id",
    ),
    # Malformed YAML front-matter (10 such files live)
    (
        "tasks/completed/TASK-FIX-CDF8/TASK-FIX-CDF8.md",
        None,
        "bad YAML",
    ),
    # ADR under a harvest-owned root — never swallowed into the tasks lane
    (
        "docs/adr/0001-adopt-agentic-flow.md",
        None,
        "harvest-owned kind: adr",
    ),
]


class TestClassifyFixtureTable:
    """The corpus-reality fixture table: real files -> named outcomes."""

    @pytest.mark.parametrize(
        ("relative_path", "expected_kind", "expected_reason"),
        FIXTURE_TABLE,
        ids=[row[0].rsplit("/", 1)[-1] for row in FIXTURE_TABLE],
    )
    def test_fixture_classification(
        self, load_doc, manifest, corpus_root, relative_path, expected_kind, expected_reason
    ) -> None:
        doc = load_doc(relative_path)
        result = classify_document(doc, manifest, corpus_root)

        assert result.skip_reason == expected_reason
        assert result.kind == expected_kind
        assert result.publishable is (expected_reason is None)

    def test_every_skip_has_a_named_reason(
        self, load_doc, manifest, corpus_root
    ) -> None:
        """No fixture is ever silently dropped: skip implies a non-empty reason."""
        for relative_path, _kind, _reason in FIXTURE_TABLE:
            result = classify_document(load_doc(relative_path), manifest, corpus_root)
            if not result.publishable:
                assert result.skip_reason, f"{relative_path} skipped without a reason"

    def test_publishable_classification_carries_frontmatter(
        self, load_doc, manifest, corpus_root
    ) -> None:
        """Publishable results carry the parsed front-matter for the parser."""
        doc = load_doc(
            "tasks/completed/2026-07/TASK-FIX-RESUMEVENV01-resume-venv-resolution.md"
        )
        result = classify_document(doc, manifest, corpus_root)
        assert result.publishable
        assert result.frontmatter is not None
        assert result.frontmatter["id"] == "TASK-FIX-RESUMEVENV01"
        assert result.frontmatter["status"] == "completed"


class TestOldContractDeleted:
    """The four-value front-matter type contract is gone outright."""

    def test_document_kind_enum_deleted(self) -> None:
        import fleet_memory.reindex.classify as classify_module

        assert not hasattr(classify_module, "DocumentKind")

    def test_dead_parser_kinds_deleted(self) -> None:
        import fleet_memory.reindex.parsers as parsers_module

        for name in ("parse_seed_module", "parse_adr", "parse_review_report"):
            assert not hasattr(parsers_module, name)
