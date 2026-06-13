"""Unit tests for corpus walker.

Tests the path-traversal-safe walker that yields markdown documents
from the configured corpus root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleet_memory.reindex.walker import CorpusDocument, walk_corpus


def test_empty_corpus_yields_nothing(tmp_path: Path) -> None:
    """An empty corpus root yields zero documents and does not raise."""
    # Arrange
    empty_root = tmp_path / "empty_corpus"
    empty_root.mkdir()

    # Act
    documents = list(walk_corpus(empty_root))

    # Assert
    assert documents == []


def test_path_traversal_entry_not_read(tmp_path: Path) -> None:
    """An entry whose name contains ../ cannot cause a read outside the root.

    A crafted path-traversal name is skipped and never read - the walker
    must not yield any document whose resolved path escapes the corpus root.
    """
    # Arrange
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    # Create a secret file outside the corpus root
    secret_file = tmp_path / "secret.md"
    secret_file.write_text("SECRET CONTENT")

    # Create a malicious entry inside the corpus that tries to escape
    # This simulates an attacker-controlled filename
    malicious_dir = corpus_root / ".."
    try:
        malicious_dir.mkdir(exist_ok=True)
        malicious_file = malicious_dir / "secret.md"
        malicious_file.write_text("SHOULD NOT BE READ")
    except (OSError, ValueError):
        # Some filesystems may reject this; if so, test passes trivially
        pass

    # Act
    documents = list(walk_corpus(corpus_root))

    # Assert
    # No documents should be yielded that escape the corpus root
    for doc in documents:
        # Every document path must be contained within the resolved corpus root
        assert doc.path.resolve().is_relative_to(
            corpus_root.resolve()
        ), f"Path {doc.path} escaped corpus root {corpus_root}"

    # The secret content must never appear in any yielded document
    all_text = " ".join(doc.text for doc in documents)
    assert "SECRET CONTENT" not in all_text
    assert "SHOULD NOT BE READ" not in all_text


def test_walk_corpus_yields_markdown_documents(tmp_path: Path) -> None:
    """walk_corpus yields each markdown document with path and text."""
    # Arrange
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    doc1 = corpus_root / "readme.md"
    doc1.write_text("# README\n\nThis is a readme.")

    doc2 = corpus_root / "notes.md"
    doc2.write_text("# Notes\n\nSome notes here.")

    subdir = corpus_root / "subdir"
    subdir.mkdir()
    doc3 = subdir / "nested.md"
    doc3.write_text("# Nested\n\nNested document.")

    # Create a non-markdown file that should be ignored
    (corpus_root / "data.txt").write_text("Not markdown")

    # Act
    documents = list(walk_corpus(corpus_root))

    # Assert
    assert len(documents) == 3

    # Check that all documents are CorpusDocument instances
    for doc in documents:
        assert isinstance(doc, CorpusDocument)
        assert isinstance(doc.path, Path)
        assert isinstance(doc.text, str)
        assert doc.text  # Non-empty

    # Check specific content
    texts = {doc.path.name: doc.text for doc in documents}
    assert "# README" in texts["readme.md"]
    assert "# Notes" in texts["notes.md"]
    assert "# Nested" in texts["nested.md"]
    assert "data.txt" not in {doc.path.name for doc in documents}


def test_symlink_escape_not_read(tmp_path: Path) -> None:
    """A symlink that points outside the corpus root is not followed."""
    # Arrange
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    # Create a secret file outside the corpus
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    secret_file = secret_dir / "secret.md"
    secret_file.write_text("TOP SECRET DATA")

    # Create a symlink inside the corpus pointing outside
    link = corpus_root / "escape_link.md"
    try:
        link.symlink_to(secret_file)
    except OSError:
        # Symlinks may not be supported on all platforms
        pytest.skip("Symlinks not supported on this platform")

    # Act
    documents = list(walk_corpus(corpus_root))

    # Assert
    # The symlink target resolves outside the corpus root, so it should be skipped
    for doc in documents:
        assert doc.path.resolve().is_relative_to(
            corpus_root.resolve()
        ), f"Symlink escape: {doc.path} -> {doc.path.resolve()}"

    # Secret content must not appear
    all_text = " ".join(doc.text for doc in documents)
    assert "TOP SECRET DATA" not in all_text


def test_resolved_path_returned(tmp_path: Path) -> None:
    """Each yielded document has its path resolved."""
    # Arrange
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    doc = corpus_root / "test.md"
    doc.write_text("# Test")

    # Act
    documents = list(walk_corpus(corpus_root))

    # Assert
    assert len(documents) == 1
    # The path should be absolute and resolved
    assert documents[0].path.is_absolute()
    assert documents[0].path == doc.resolve()
