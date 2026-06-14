"""Tests for the re-index orchestrator pipeline.

Tests verify the orchestrator coordinates walker, classifier, parser, and publisher
to process a full corpus, producing a RunReport that accounts for every document.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from fleet_memory.payloads.base import BasePayload
from fleet_memory.reindex.pipeline import reindex_corpus


@dataclass(frozen=True)
class FakePublisher:
    """Test double for capturing published episodes."""

    published: list[BasePayload]

    async def publish(self, payload: BasePayload) -> None:
        """Capture published payload."""
        self.published.append(payload)


def _create_test_corpus(tmp_path: Path, documents: dict[str, str]) -> Path:
    """Create a test corpus with the given documents.

    Args:
        tmp_path: Temporary directory for the corpus
        documents: Mapping of filename to content

    Returns:
        Path to the corpus root
    """
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    for filename, content in documents.items():
        doc_path = corpus_root / filename
        doc_path.write_text(content, encoding="utf-8")

    return corpus_root


@pytest.mark.asyncio
async def test_full_corpus_publishes_one_episode_per_recognized_doc(tmp_path: Path):
    """Verify full corpus run publishes exactly one episode per recognized document.

    Acceptance criteria: Every recognized document is published as a typed episode.
    """
    # Create corpus with multiple recognized documents
    documents = {
        "seed_module.md": """---
type: seed_module
project: test_project
identifier: core_auth
module_path: src/auth.py
---
# Seed Module
""",
        "adr.md": """---
type: adr
project: test_project
identifier: ADR_001
decision: Use PostgreSQL
status: accepted
---
# ADR
""",
        "review.md": """---
type: review_report
project: test_project
identifier: REV_001
verdict: approved
---
# Review Report
""",
    }
    corpus_root = _create_test_corpus(tmp_path, documents)

    # Run pipeline with fake publisher
    published: list[BasePayload] = []
    fake_publisher = FakePublisher(published=published)

    report = await reindex_corpus(
        corpus_root=corpus_root,
        publisher=fake_publisher.publish,
    )

    # Verify one episode per recognized document
    assert len(published) == 3, f"Expected 3 episodes, got {len(published)}"
    assert report.published_count == 3
    assert report.unparseable_count == 0
    assert report.unrecognized_count == 0


@pytest.mark.asyncio
async def test_single_unparseable_doc_does_not_abort_run(tmp_path: Path):
    """Verify a single unparseable document does not abort the full corpus run.

    Acceptance criteria: One bad document does not prevent publishing valid documents.
    """
    # Create corpus with one bad document and two good ones
    documents = {
        "good1.md": """---
type: seed_module
project: test_project
identifier: module_1
module_path: src/module1.py
---
# Good Module 1
""",
        "bad.md": """---
type: seed_module
project: test_project
# Missing required field: identifier
module_path: src/bad.py
---
# Bad Module
""",
        "good2.md": """---
type: adr
project: test_project
identifier: ADR_002
decision: Use async
status: accepted
---
# Good ADR
""",
    }
    corpus_root = _create_test_corpus(tmp_path, documents)

    # Run pipeline
    published: list[BasePayload] = []
    fake_publisher = FakePublisher(published=published)

    report = await reindex_corpus(
        corpus_root=corpus_root,
        publisher=fake_publisher.publish,
    )

    # Verify good documents were published despite the bad one
    assert len(published) == 2, "Both good documents should be published"
    assert report.published_count == 2
    assert report.unparseable_count == 1
    assert report.unrecognized_count == 0

    # Verify bad document is in unparseable list with reason
    assert len(report.unparseable) == 1
    unparseable = report.unparseable[0]
    assert "identifier" in unparseable["reason"].lower()


@pytest.mark.asyncio
async def test_empty_corpus_publishes_nothing(tmp_path: Path):
    """Verify empty corpus completes cleanly without publishing anything.

    Acceptance criteria: Empty corpus publishes nothing and completes successfully.
    """
    # Create empty corpus directory
    corpus_root = tmp_path / "empty_corpus"
    corpus_root.mkdir()

    # Run pipeline
    published: list[BasePayload] = []
    fake_publisher = FakePublisher(published=published)

    report = await reindex_corpus(
        corpus_root=corpus_root,
        publisher=fake_publisher.publish,
    )

    # Verify nothing was published
    assert len(published) == 0
    assert report.published_count == 0
    assert report.unparseable_count == 0
    assert report.unrecognized_count == 0


@pytest.mark.asyncio
async def test_report_accounts_for_every_walked_document(tmp_path: Path):
    """Verify RunReport accounts for every document walked.

    Acceptance criteria: published + unparseable + unrecognized = total walked.
    """
    # Create corpus with all three categories
    documents = {
        "recognized.md": """---
type: seed_module
project: test_project
identifier: module_recognized
module_path: src/recognized.py
---
# Recognized
""",
        "unparseable.md": """---
type: seed_module
project: test_project
# Missing required field: identifier
---
# Unparseable
""",
        "unrecognized.md": """---
type: unknown_type
---
# Unrecognized
""",
        "no_frontmatter.md": """# Just a markdown file
No frontmatter at all.
""",
    }
    corpus_root = _create_test_corpus(tmp_path, documents)

    # Run pipeline
    published: list[BasePayload] = []
    fake_publisher = FakePublisher(published=published)

    report = await reindex_corpus(
        corpus_root=corpus_root,
        publisher=fake_publisher.publish,
    )

    # Verify accounting: every document is accounted for
    total_walked = 4
    total_accounted = (
        report.published_count + report.unparseable_count + report.unrecognized_count
    )
    assert total_accounted == total_walked, (
        f"Accounting mismatch: {report.published_count} published + "
        f"{report.unparseable_count} unparseable + "
        f"{report.unrecognized_count} unrecognized = "
        f"{total_accounted}, but walked {total_walked} documents"
    )

    # Verify categorization
    assert report.published_count == 1
    assert report.unparseable_count == 1
    assert report.unrecognized_count == 2  # unknown_type + no_frontmatter
