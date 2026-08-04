"""Path-traversal-safe corpus walker for fleet-memory reindexing.

The walker yields candidate markdown documents rooted at a configured corpus root.
Security property: never reads outside the corpus root, even when an entry name
contains .. segments or a symlink that escapes the root.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusDocument:
    """A candidate document from the corpus with its resolved path and raw text.

    Attributes:
        path: Absolute, resolved path to the document (guaranteed within corpus root)
        text: Raw text content of the document
    """

    path: Path
    text: str


def walk_corpus(root: Path) -> Iterator[CorpusDocument]:
    """Yield each markdown document under root with resolved path and raw text.

    The walker enforces the security invariant that every yielded path, after
    Path.resolve(), is contained within the resolved corpus root. Entries
    containing path-traversal segments or symlinks that escape are skipped
    and never read.

    Args:
        root: The corpus root directory to walk

    Yields:
        CorpusDocument instances for each .md file within the corpus root

    Example:
        >>> for doc in walk_corpus(Path("/corpus")):
        ...     print(f"{doc.path}: {len(doc.text)} bytes")
    """
    # Resolve the root once to establish the containment boundary
    resolved_root = root.resolve()

    # Ensure root exists and is a directory
    if not resolved_root.exists():
        return
    if not resolved_root.is_dir():
        return

    yield from _walk_within(resolved_root, resolved_root)


def walk_roots(corpus_root: Path, relative_roots: list[str]) -> Iterator[CorpusDocument]:
    """Yield markdown documents under ONLY the given repo-relative roots.

    This is the structural fix for corpus inflation: the reindex pipeline walks
    the manifest's reindex-owned directories (e.g. tasks/completed, 2,286 files)
    instead of the whole checkout (63,683 files once .guardkit/worktrees is
    swept in). Decoy trees full of .md files outside the roots are never read.

    The same path-traversal safety invariant as walk_corpus holds: every yielded
    path, after Path.resolve(), is contained within the resolved corpus root. A
    relative root that escapes the corpus root (.. segments, symlinks out) is
    skipped entirely and never read.

    Args:
        corpus_root: The corpus root directory (repository checkout root)
        relative_roots: Repo-relative directory paths to descend

    Yields:
        CorpusDocument instances for each .md file within the selected roots
    """
    resolved_corpus_root = corpus_root.resolve()

    if not resolved_corpus_root.exists() or not resolved_corpus_root.is_dir():
        return

    for relative_root in relative_roots:
        candidate_root = resolved_corpus_root / relative_root

        # Resolve the candidate root and enforce containment BEFORE descending
        try:
            resolved_dir = candidate_root.resolve()
        except (OSError, RuntimeError):
            continue

        try:
            if not resolved_dir.is_relative_to(resolved_corpus_root):
                # Root escapes the corpus root - never descend it
                continue
        except ValueError:
            continue

        if not resolved_dir.exists() or not resolved_dir.is_dir():
            continue

        yield from _walk_within(resolved_dir, resolved_corpus_root)


def _walk_within(scan_root: Path, containment_root: Path) -> Iterator[CorpusDocument]:
    """Yield .md documents under scan_root, containment-checked against containment_root.

    Args:
        scan_root: Resolved directory to enumerate
        containment_root: Resolved boundary every yielded path must stay within

    Yields:
        CorpusDocument instances for each safe, readable .md file
    """
    for entry in scan_root.rglob("*"):
        # Skip directories
        if not entry.is_file():
            continue

        # Only process markdown files
        if entry.suffix.lower() != ".md":
            continue

        # Resolve the candidate path
        try:
            resolved_entry = entry.resolve()
        except (OSError, RuntimeError):
            # Resolution may fail for broken symlinks or circular references
            continue

        # SECURITY: Assert containment - this is the single line that enforces
        # the path-traversal safety invariant
        try:
            if not resolved_entry.is_relative_to(containment_root):
                # Entry escapes the corpus root - skip it
                continue
        except ValueError:
            # is_relative_to may raise on some platforms
            continue

        # Read the document content
        try:
            text = resolved_entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Skip files that cannot be read or decoded
            continue

        # Yield the validated document
        yield CorpusDocument(path=resolved_entry, text=text)
