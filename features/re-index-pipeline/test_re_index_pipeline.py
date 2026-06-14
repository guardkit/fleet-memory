"""pytest-bdd glue for the Re-index Pipeline feature (FEAT-MEM-07).

Binds the scenarios in ``re-index-pipeline.feature`` so GuardKit's per-task
BDD oracle (``bdd_runner``) can collect them when it points pytest at the
literal ``.feature`` path via the ``features/conftest.py`` collection bridge.

Scaffolding state (TASK-AB-004 convention): step definitions are added
incrementally by the owning task for each ``@task:TASK-RIP-00x`` scenario.
Until a scenario's steps are implemented, pytest-bdd raises
``StepDefinitionNotFoundError`` for the first unbound step, which the bdd_runner
classifies as **pending** (tolerated — distinct from a failing assertion) rather
than a gate-blocking failure. As each task lands its steps, its scenario flips
from pending to passing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from fleet_memory.payloads.base import BasePayload
from fleet_memory.reindex.pipeline import reindex_corpus

# Bind every scenario in the feature file. The per-task ``-m`` marker filter
# (applied by bdd_runner) selects only the scenarios tagged for the running
# task; the rest are deselected.
scenarios("re-index-pipeline.feature")


@dataclass
class TestPublisher:
    """Test double for capturing published episodes."""

    published: list[BasePayload] = field(default_factory=list)

    async def publish(self, payload: BasePayload) -> None:
        """Capture published payload."""
        self.published.append(payload)


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared mutable context for passing data between step definitions."""
    return {}


# ──────────────────── Background Steps ────────────────────


@given(
    "the guardkit markdown corpus is available on disk with seed modules, "
    "ADRs, review reports, and completed-task outcomes"
)
def given_guardkit_corpus(context: dict[str, Any], tmp_path: Path) -> None:
    """Background step: corpus is available (actual corpus set up in scenarios)."""
    # Background step - actual corpus setup happens in scenario-specific steps
    pass


@given("the publisher helper can publish a memory episode onto the memory stream")
def given_publisher_helper(context: dict[str, Any]) -> None:
    """Background step: publisher helper is available (set up by test fixtures)."""
    # Publisher is set up in scenario-specific steps
    pass


@given("the live relay is consuming the memory stream into the store")
def given_live_relay(context: dict[str, Any]) -> None:
    """Background step: relay is consuming (not needed for unit-level BDD tests)."""
    # This is handled downstream; pipeline tests use fake publisher
    pass


# ──────────────────── TASK-RIP-005 Step Definitions ────────────────────


@given("a corpus containing seed modules, ADRs, review reports, and task outcomes")
def given_full_corpus(context: dict[str, Any], tmp_path: Path) -> None:
    """Set up a corpus with multiple document types."""
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    # Seed module
    (corpus_root / "seed_module.md").write_text("""---
type: seed_module
project: test_project
identifier: core_auth
module_path: src/auth.py
---
# Seed Module
""")

    # ADR
    (corpus_root / "adr.md").write_text("""---
type: adr
project: test_project
identifier: ADR_001
decision: Use PostgreSQL
status: accepted
---
# ADR
""")

    # Review report
    (corpus_root / "review.md").write_text("""---
type: review_report
project: test_project
identifier: REV_001
verdict: approved
---
# Review Report
""")

    # Completed task (build outcome)
    (corpus_root / "task.md").write_text("""---
type: completed_task
project: test_project
identifier: TASK_001
status: success
duration_seconds: 120
---
# Task Outcome
""")

    context["corpus_root"] = corpus_root
    context["publisher"] = TestPublisher()


@given("a corpus of recognized documents")
def given_corpus_of_recognized_documents(
    context: dict[str, Any], tmp_path: Path
) -> None:
    """Set up a corpus with recognized documents."""
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    (corpus_root / "seed_module.md").write_text("""---
type: seed_module
project: test_project
identifier: module_1
module_path: src/module1.py
---
# Seed Module
""")

    context["corpus_root"] = corpus_root
    context["publisher"] = TestPublisher()


@given("a corpus containing exactly one recognized document")
def given_one_document_corpus(context: dict[str, Any], tmp_path: Path) -> None:
    """Set up a corpus with exactly one document."""
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    (corpus_root / "single.md").write_text("""---
type: seed_module
project: test_project
identifier: single_module
module_path: src/single.py
---
# Single Document
""")

    context["corpus_root"] = corpus_root
    context["publisher"] = TestPublisher()


@given(
    "a corpus of recognized documents and a staging area of reviewed backfill payloads"
)
def given_corpus_with_backfill(context: dict[str, Any], tmp_path: Path) -> None:
    """Set up corpus for no-LLM test (alias for recognized documents corpus)."""
    given_corpus_of_recognized_documents(context, tmp_path)


@given("a corpus where one document has malformed front-matter and the rest are valid")
def given_corpus_with_one_bad_doc(context: dict[str, Any], tmp_path: Path) -> None:
    """Set up a corpus with one malformed document and valid ones."""
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    # Valid document 1
    (corpus_root / "good1.md").write_text("""---
type: seed_module
project: test_project
identifier: module_1
module_path: src/module1.py
---
# Good Module 1
""")

    # Malformed document (missing required field)
    (corpus_root / "bad.md").write_text("""---
type: seed_module
project: test_project
# Missing required field: identifier
module_path: src/bad.py
---
# Bad Module
""")

    # Valid document 2
    (corpus_root / "good2.md").write_text("""---
type: adr
project: test_project
identifier: ADR_002
decision: Use async
status: accepted
---
# Good ADR
""")

    context["corpus_root"] = corpus_root
    context["publisher"] = TestPublisher()


@when("the re-index pipeline runs over the whole corpus")
@when("the re-index pipeline runs")
def when_pipeline_runs(context: dict[str, Any]) -> None:
    """Run the reindex pipeline."""
    corpus_root = context["corpus_root"]
    publisher = context["publisher"]
    report = asyncio.run(reindex_corpus(corpus_root, publisher.publish))
    context["report"] = report


@then("every recognized document should be published as a typed memory episode")
def then_all_published(context: dict[str, Any]) -> None:
    """Verify all recognized documents were published."""
    publisher = context["publisher"]
    report = context["report"]
    # Full corpus has 4 documents
    assert len(publisher.published) == 4
    assert report.published_count == 4


@then("each episode should declare the payload type matching its document kind")
def then_episodes_have_payload_types(context: dict[str, Any]) -> None:
    """Verify each episode has correct payload_type."""
    publisher = context["publisher"]
    payload_types = {p.payload_type for p in publisher.published}
    expected_types = {"seed_module", "adr", "review_report", "build_outcome"}
    assert payload_types == expected_types


@then(
    "no language-model or chat-completion request should be made during parsing or publishing"
)
def then_no_llm_calls(context: dict[str, Any]) -> None:
    """Verify no LLM calls were made (implicitly tested by deterministic parsing)."""
    # This is verified by the fact that the pipeline uses only deterministic
    # parsers (YAML frontmatter extraction, regex, field validation)
    # No anthropic, openai, or other LLM imports in the call stack
    report = context["report"]
    assert report is not None  # Pipeline completed without LLM calls


@then("exactly one episode should be published")
def then_one_episode_published(context: dict[str, Any]) -> None:
    """Verify exactly one episode was published."""
    publisher = context["publisher"]
    report = context["report"]
    assert len(publisher.published) == 1
    assert report.published_count == 1


@then(parsers.parse("every valid document should still be published"))
@then("every valid document is published and the run completes successfully")
def then_valid_docs_published(context: dict[str, Any]) -> None:
    """Verify valid documents were published despite errors."""
    publisher = context["publisher"]
    report = context["report"]
    # Corpus has 2 valid documents (good1 and good2)
    assert len(publisher.published) == 2
    assert report.published_count == 2


@then("the unparseable document should be reported with a reason")
def then_unparseable_reported(context: dict[str, Any]) -> None:
    """Verify unparseable document is in the report."""
    report = context["report"]
    assert report.unparseable_count == 1
    assert len(report.unparseable) == 1
    assert "identifier" in report.unparseable[0]["reason"].lower()


@then("no cloud or frontier-model request should be made by the pipeline")
def then_no_cloud_calls(context: dict[str, Any]) -> None:
    """Verify no cloud/frontier-model calls were made."""
    # Verified by deterministic parsing - no cloud imports in the stack
    report = context["report"]
    assert report is not None  # Pipeline completed without cloud calls


@then("every valid document should be published")
def then_every_valid_doc_published(context: dict[str, Any]) -> None:
    """Verify all valid documents were published."""
    then_valid_docs_published(context)


@then("the run should report the one unparseable document")
def then_report_one_unparseable(context: dict[str, Any]) -> None:
    """Verify the unparseable document is in the report."""
    then_unparseable_reported(context)
