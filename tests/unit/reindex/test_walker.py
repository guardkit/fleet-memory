"""Unit tests for corpus walker.

Tests the path-traversal-safe walker that yields markdown documents
from the configured corpus root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleet_memory.reindex.walker import CorpusDocument, walk_corpus, walk_roots


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


class TestWalkRoots:
    """walk_roots descends ONLY the manifest's reindex-owned directories.

    This is the structural kill for the 63,683-file worktree inflation: decoy
    trees full of .md files outside the roots are never read.
    """

    def test_descends_only_given_roots(self, tmp_path: Path) -> None:
        # Reindex-owned root
        tasks = tmp_path / "tasks" / "completed"
        tasks.mkdir(parents=True)
        (tasks / "TASK-1.md").write_text("# Task 1")

        # Decoy: a .guardkit/worktrees tree full of markdown (the live corpus
        # carries 63k files here — walking it was the inflation)
        decoy = tmp_path / ".guardkit" / "worktrees" / "FEAT-X" / "tasks" / "completed"
        decoy.mkdir(parents=True)
        for i in range(5):
            (decoy / f"TASK-DECOY-{i}.md").write_text("# Decoy")

        # Other repo content outside the roots
        (tmp_path / "README.md").write_text("# Readme")

        documents = list(walk_roots(tmp_path, ["tasks/completed"]))

        assert len(documents) == 1
        assert documents[0].path.name == "TASK-1.md"

    def test_multiple_roots(self, tmp_path: Path) -> None:
        for root in ("tasks/completed", "tasks/archive"):
            directory = tmp_path / root
            directory.mkdir(parents=True)
            (directory / "doc.md").write_text("# Doc")

        documents = list(walk_roots(tmp_path, ["tasks/completed", "tasks/archive"]))
        assert len(documents) == 2

    def test_missing_root_is_skipped(self, tmp_path: Path) -> None:
        documents = list(walk_roots(tmp_path, ["tasks/completed"]))
        assert documents == []

    def test_root_escaping_corpus_never_descended(self, tmp_path: Path) -> None:
        """Same traversal-safety invariant as walk_corpus: a relative root with
        .. segments must never cause reads outside the corpus root."""
        corpus_root = tmp_path / "corpus"
        corpus_root.mkdir()
        secret_dir = tmp_path / "secrets"
        secret_dir.mkdir()
        (secret_dir / "secret.md").write_text("TOP SECRET DATA")

        documents = list(walk_roots(corpus_root, ["../secrets"]))

        assert documents == []

    def test_symlinked_root_escaping_corpus_never_descended(self, tmp_path: Path) -> None:
        corpus_root = tmp_path / "corpus"
        corpus_root.mkdir()
        secret_dir = tmp_path / "secrets"
        secret_dir.mkdir()
        (secret_dir / "secret.md").write_text("TOP SECRET DATA")

        link = corpus_root / "tasks"
        try:
            link.symlink_to(secret_dir, target_is_directory=True)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        documents = list(walk_roots(corpus_root, ["tasks"]))

        assert documents == []

    def test_symlink_file_escape_inside_root_not_read(self, tmp_path: Path) -> None:
        corpus_root = tmp_path / "corpus"
        tasks = corpus_root / "tasks" / "completed"
        tasks.mkdir(parents=True)
        (tasks / "real.md").write_text("# Real")

        secret = tmp_path / "secret.md"
        secret.write_text("TOP SECRET DATA")
        link = tasks / "escape.md"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        documents = list(walk_roots(corpus_root, ["tasks/completed"]))

        assert len(documents) == 1
        assert documents[0].path.name == "real.md"
        all_text = " ".join(doc.text for doc in documents)
        assert "TOP SECRET DATA" not in all_text

    def test_only_markdown_yielded(self, tmp_path: Path) -> None:
        tasks = tmp_path / "tasks" / "completed"
        tasks.mkdir(parents=True)
        (tasks / "doc.md").write_text("# Doc")
        (tasks / "data.json").write_text("{}")
        (tasks / "notes.txt").write_text("text")

        documents = list(walk_roots(tmp_path, ["tasks/completed"]))
        assert [doc.path.name for doc in documents] == ["doc.md"]
