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

    # Walk all entries under the root
    for entry in resolved_root.rglob("*"):
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
            if not resolved_entry.is_relative_to(resolved_root):
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
