"""Corpus-reality document classification for fleet-memory reindexing.

Classification is PATH-FIRST: the document's kind comes from the corpus manifest
(longest-prefix match on its repo-relative path), never from a front-matter
``type:`` field. Corpus reality killed the front-matter type contract: of 2,286
live files under tasks/completed, zero carry ``type: completed_task`` — the old
four-value contract classified everything "unrecognized" and published nothing
("70,903 processed, 0 published").

For the tasks lane (kind ``build_outcome``) a file is publishable only when its
YAML front-matter carries an ``id`` AND a TERMINAL status (completed /
review_complete / closed / superseded, case-insensitive). Live census: 2,286 md
files, 1,675 with front-matter, 1,561 with a terminal status.

Security property: EVERY non-publishable file gets a named skip reason — never
guessed at, never silently dropped (ASSUM-004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fleet_memory.reindex.manifest import CorpusManifest
from fleet_memory.reindex.walker import CorpusDocument

# Terminal task statuses (case-insensitive): the file describes finished work.
# Everything else (backlog, in_progress, blocked, template garbage like
# "{status}") is curation noise that must not enter the store.
TERMINAL_STATUSES = frozenset({"completed", "review_complete", "closed", "superseded"})

# Agent-definition front-matter shape: these .md files live under tasks/completed
# (e.g. tasks/completed/agent-enhancement-implementation/agents/) but describe
# agents, not build outcomes. Live census: 16 such files.
AGENT_DEFINITION_KEYS = frozenset({"name", "model", "tools"})


@dataclass(frozen=True)
class Classification:
    """Result of classifying one corpus document.

    Exactly one of two outcomes:
    - publishable: kind is set, skip_reason is None
    - skipped: skip_reason names why (never silently dropped)

    Attributes:
        document_path: Source document path for accounting
        kind: Manifest kind when publishable (e.g. "build_outcome")
        frontmatter: Parsed front-matter dict when available (reused by parsers)
        skip_reason: Named reason when not publishable
    """

    document_path: Path
    kind: str | None = None
    frontmatter: dict[str, Any] | None = None
    skip_reason: str | None = None

    @property
    def publishable(self) -> bool:
        """True when the document should be parsed and published."""
        return self.skip_reason is None


def extract_frontmatter(text: str) -> dict[str, Any] | None:
    """Extract and parse YAML front-matter from markdown text.

    Args:
        text: Raw markdown document text

    Returns:
        Parsed front-matter dict, or None if no front-matter found

    Raises:
        yaml.YAMLError: If front-matter exists but is malformed
    """
    # Match YAML front-matter block: --- ... ---
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, text, re.DOTALL)

    if not match:
        return None

    yaml_content = match.group(1)
    # This may raise yaml.YAMLError if malformed
    return yaml.safe_load(yaml_content)


def _repo_relative_path(doc: CorpusDocument, corpus_root: Path) -> str:
    """Compute the document's repo-relative path with forward slashes."""
    relative = doc.path.resolve().relative_to(corpus_root.resolve())
    return str(relative).replace("\\", "/")


def classify_document(
    doc: CorpusDocument,
    manifest: CorpusManifest,
    corpus_root: Path,
) -> Classification:
    """Classify a corpus document: path-first kind, front-matter gate for tasks.

    Only owner=="reindex" roots are ever walked, so in normal operation every
    document resolves to a reindex-owned kind; the harvest-owned and
    outside-manifest branches are defensive accounting, never silent drops.

    Args:
        doc: Corpus document to classify
        manifest: Corpus manifest (ownership + kind resolution)
        corpus_root: Repository checkout root the corpus was walked from

    Returns:
        Classification — publishable with a kind, or skipped with a named reason
    """
    relative_path = _repo_relative_path(doc, corpus_root)

    resolved = manifest.resolve_kind(relative_path)
    if resolved is None:
        return Classification(
            document_path=doc.path,
            skip_reason="path outside manifest roots",
        )

    kind, owner = resolved
    if owner != "reindex":
        # Harvest-owned paths (docs/adr, docs/code-review, ...) belong to
        # guardkit's prose harvester — publishing them here would double-publish.
        return Classification(
            document_path=doc.path,
            skip_reason=f"harvest-owned kind: {kind}",
        )

    # Tasks lane gate: front-matter with id + TERMINAL status
    try:
        frontmatter = extract_frontmatter(doc.text)
    except yaml.YAMLError:
        return Classification(document_path=doc.path, skip_reason="bad YAML")

    if frontmatter is None:
        return Classification(document_path=doc.path, skip_reason="no front-matter")

    if not isinstance(frontmatter, dict):
        # Front-matter parsed to a scalar/list — it cannot carry an id
        return Classification(
            document_path=doc.path,
            skip_reason="front-matter without id",
        )

    if AGENT_DEFINITION_KEYS.issubset(frontmatter.keys()):
        return Classification(
            document_path=doc.path,
            frontmatter=frontmatter,
            skip_reason="agent-definition shape (name/model/tools keys)",
        )

    if not frontmatter.get("id"):
        return Classification(
            document_path=doc.path,
            frontmatter=frontmatter,
            skip_reason="front-matter without id",
        )

    status = str(frontmatter.get("status", "")).strip()
    if status.lower() not in TERMINAL_STATUSES:
        return Classification(
            document_path=doc.path,
            frontmatter=frontmatter,
            skip_reason=f"non-terminal status: {status or '(missing)'}",
        )

    return Classification(
        document_path=doc.path,
        kind=kind,
        frontmatter=frontmatter,
    )
