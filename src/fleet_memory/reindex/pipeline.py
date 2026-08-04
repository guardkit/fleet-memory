"""Re-index orchestrator: manifest-driven walk → classify → parse → publish.

The pipeline walks ONLY the manifest's reindex-owned roots (walk_roots — the
structural fix for the 63,683-file worktree inflation), classifies path-first,
parses publishable tasks, resolves within-run id collisions, preserves existing
lessons prose, and publishes typed episodes.

Accounting invariant: walked == published + skipped + unparseable. Every walked
document lands in exactly one bucket with a named reason when it does not publish.

Security: one bad document never aborts the full run. Empty corpus completes cleanly.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fleet_memory.reindex.classify import classify_document
from fleet_memory.reindex.manifest import CorpusManifest
from fleet_memory.reindex.parsers import (
    ParsedPayload,
    UnparseableDocument,
    parse_completed_task,
)
from fleet_memory.reindex.walker import walk_roots
from fleet_memory.writer.identity import record_identity

if TYPE_CHECKING:
    from fleet_memory.payloads.base import BasePayload

# Publisher callable: returns None on success or a named skip reason.
# None publisher = census mode (--dry-run): documents are counted, not published.
PublisherFn = Callable[["BasePayload"], Awaitable[str | None]]


@dataclass(frozen=True)
class RunReport:
    """Accounting report for a full corpus reindex run.

    Invariant: walked_count == published_count + skipped_count + unparseable_count.

    Attributes:
        walked_count: Number of documents yielded by the walker
        published_count: Number of successfully published episodes
        skipped_count: Number of documents skipped with a named reason
        unparseable_count: Number of publishable-classified documents that failed parsing
        per_kind_counts: Published episode count per manifest kind
        published_natural_keys: Natural keys of every published episode (audit input)
        skipped: List of {path, reason} for every skipped document
        unparseable: List of {path, reason} for every unparseable document
    """

    walked_count: int = 0
    published_count: int = 0
    skipped_count: int = 0
    unparseable_count: int = 0
    per_kind_counts: dict[str, int] = field(default_factory=dict)
    published_natural_keys: list[str] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    unparseable: list[dict[str, Any]] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize the report for the run-report JSON file."""
        return {
            "walked_count": self.walked_count,
            "published_count": self.published_count,
            "skipped_count": self.skipped_count,
            "unparseable_count": self.unparseable_count,
            "per_kind_counts": dict(self.per_kind_counts),
            "published_natural_keys": list(self.published_natural_keys),
            "skipped": list(self.skipped),
            "unparseable": list(self.unparseable),
        }


@dataclass
class _Candidate:
    """A publishable, parsed document awaiting collision resolution."""

    relative_path: str
    title: str | None
    payload: BasePayload
    kind: str


def _relative_path(path: Path, corpus_root: Path) -> str:
    """Repo-relative path with forward slashes (best-effort for reporting)."""
    try:
        return str(path.resolve().relative_to(corpus_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _resolve_collisions(
    candidates: list[_Candidate],
    skipped: list[dict[str, Any]],
) -> list[_Candidate]:
    """Apply the within-run id collision policy (40 duplicate ids live).

    - same identifier + same title: collapse — the deepest path wins, the
      shadowed paths are recorded in the report.
    - same identifier + DIFFERENT titles (20 distinct tasks live): skip BOTH
      with a named reason. Which task owns the id is a curation ruling, never
      a silent last-wins.
    """
    by_identifier: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        by_identifier.setdefault(candidate.payload.identifier, []).append(candidate)

    winners: list[_Candidate] = []
    for group in by_identifier.values():
        if len(group) == 1:
            winners.append(group[0])
            continue

        titles = {candidate.title for candidate in group}
        paths = sorted(candidate.relative_path for candidate in group)

        if len(titles) > 1:
            # Distinct tasks sharing an id: a curation ruling, never silent last-wins
            reason = f"id collision across distinct tasks: {paths}"
            for candidate in group:
                skipped.append({"path": candidate.relative_path, "reason": reason})
            continue

        # Same task duplicated (archived copy vs monthly folder): deepest path wins
        winner = max(
            group,
            key=lambda c: (len(Path(c.relative_path).parts), c.relative_path),
        )
        winners.append(winner)
        for candidate in group:
            if candidate is winner:
                continue
            skipped.append(
                {
                    "path": candidate.relative_path,
                    "reason": (
                        "id collision (same task): shadowed by deeper path "
                        f"{winner.relative_path}"
                    ),
                }
            )

    return winners


async def _preserve_existing_lessons(payload: BasePayload, store: Any) -> BasePayload:
    """Carry existing stored lessons forward when the outgoing payload has none.

    Read-before-write: only 73/1,545 corpus files carry a lessons section, but
    ~130 export-seeded rows already hold distilled lessons prose. Without this
    merge, ~95% of the overlapping re-publishes would null real lessons. It also
    minimizes version churn: when nothing else changed, the carried-forward
    payload content-hashes identically and the writer no-ops.
    """
    if getattr(payload, "lessons", "missing") is not None:
        return payload

    natural_key = payload.natural_key
    namespace = ("fleet_memory", payload.project, payload.payload_type)
    store_key = str(record_identity(natural_key))

    existing = await store.aget(namespace, store_key)
    if existing is None:
        return payload

    existing_value = getattr(existing, "value", None) or {}
    content = existing_value.get("content")
    try:
        existing_payload = json.loads(content) if content else {}
    except (TypeError, json.JSONDecodeError):
        return payload

    existing_lessons = existing_payload.get("lessons")
    if not existing_lessons:
        return payload

    return payload.model_copy(update={"lessons": existing_lessons})


async def reindex_corpus(
    corpus_root: Path,
    manifest: CorpusManifest,
    publisher: PublisherFn | None,
    store: Any = None,
) -> RunReport:
    """Orchestrate a full corpus reindex run.

    Phases:
    1. Walk ONLY the manifest's reindex-owned roots (walk_roots)
    2. Classify path-first; skip with named reasons
    3. Parse publishable documents into typed payloads
    4. Resolve within-run id collisions (collapse same-task, skip distinct-task)
    5. Preserve existing stored lessons (read-before-write, when store given)
    6. Publish (or census-count when publisher is None for --dry-run)

    Args:
        corpus_root: Repository checkout root of the corpus
        manifest: Validated corpus manifest (ownership + kinds)
        publisher: Async publish callable returning None or a skip reason;
            None runs a census with no store/NATS connections
        store: Optional AsyncPostgresStore-compatible store for lessons
            preservation (aget only)

    Returns:
        RunReport satisfying walked == published + skipped + unparseable
    """
    walked_count = 0
    skipped: list[dict[str, Any]] = []
    unparseable: list[dict[str, Any]] = []
    candidates: list[_Candidate] = []

    for doc in walk_roots(corpus_root, manifest.reindex_roots()):
        walked_count += 1
        relative_path = _relative_path(doc.path, corpus_root)

        classification = classify_document(doc, manifest, corpus_root)
        if not classification.publishable:
            skipped.append({"path": relative_path, "reason": classification.skip_reason})
            continue

        try:
            parse_result = parse_completed_task(
                doc, corpus_root, frontmatter=classification.frontmatter
            )
        except Exception as e:  # One bad document never aborts the run
            unparseable.append({"path": relative_path, "reason": f"Parser error: {e}"})
            continue

        if isinstance(parse_result, UnparseableDocument):
            unparseable.append(
                {"path": relative_path, "reason": parse_result.reason}
            )
            continue

        assert isinstance(parse_result, ParsedPayload)
        frontmatter = classification.frontmatter or {}
        title = frontmatter.get("title")
        candidates.append(
            _Candidate(
                relative_path=relative_path,
                title=str(title) if title is not None else None,
                payload=parse_result.payload,
                kind=classification.kind or "build_outcome",
            )
        )

    winners = _resolve_collisions(candidates, skipped)

    published_natural_keys: list[str] = []
    per_kind_counts: dict[str, int] = {}

    for candidate in winners:
        payload = candidate.payload

        if store is not None:
            payload = await _preserve_existing_lessons(payload, store)

        if publisher is not None:
            skip_reason = await publisher(payload)
            if skip_reason is not None:
                skipped.append({"path": candidate.relative_path, "reason": skip_reason})
                continue

        published_natural_keys.append(payload.natural_key)
        per_kind_counts[candidate.kind] = per_kind_counts.get(candidate.kind, 0) + 1

    return RunReport(
        walked_count=walked_count,
        published_count=len(published_natural_keys),
        skipped_count=len(skipped),
        unparseable_count=len(unparseable),
        per_kind_counts=per_kind_counts,
        published_natural_keys=published_natural_keys,
        skipped=skipped,
        unparseable=unparseable,
    )
