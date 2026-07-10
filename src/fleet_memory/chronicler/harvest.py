"""Pure harvest logic for the Chronicler (zero store/IO imports).

Transforms materialized episode records into the two DF-008-split outputs:

- **dataset rows** — flywheel-tagged ShareGPT rows, produced by per-type extractors from
  episodes that carry a learnable signal (build retros, planning-assumption refinements).
  Rows are PRIVATE and carry full flywheel provenance including a confidentiality flag.
- **story cards** — one per story (grouped on the correlation spine), a draft markdown
  card carrying a confidentiality flag and ``published: false`` (the human gate).

The ``source: flywheel`` enum is reserved by the factory for exactly this Chronicler
(agentic-dataset-factory: ``synthetic | harvest | flywheel``). Everything here is pure and
deterministic given its inputs (no clock, no IO), so it is fully unit-testable.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from fleet_memory.payloads.norm import norm

#: The flywheel source enum value (agentic-dataset-factory provenance).
FLYWHEEL_SOURCE = "flywheel"

#: Confidentiality flags (DF-008). Default is the safe one.
CONFIDENTIAL = "confidential"
PUBLIC = "public"

_SYSTEM_PROMPT = (
    "You are a factory agent learning from the fleet's own delivery history. "
    "Given the context of a real work event, produce the lesson or refinement it teaches."
)

# Payload fields, in preference order, that identify the story a row/episode belongs to.
_STORY_KEY_FIELDS = ("correlation_id", "feat_id", "spec_id", "task_id")


@dataclass
class HarvestedEpisode:
    """One materialized episode record read from the durable store.

    ``payload`` is the typed payload's own fields (the parsed ``content`` JSON); the
    remaining fields come from the stored record / envelope metadata.
    """

    project: str
    payload_type: str
    natural_key: str
    identifier: str
    payload: dict[str, Any]
    source_ref: str | None = None
    occurred_at: str | None = None
    name: str | None = None
    source: str | None = None

    def story_key(self) -> str:
        """The story this episode belongs to (correlation spine, then work-item ids)."""
        for key_field in _STORY_KEY_FIELDS:
            value = self.payload.get(key_field)
            if value:
                return str(value)
        return self.natural_key or self.identifier


@dataclass
class StoryCard:
    """A draft story card destined for the human review queue (DF-008)."""

    story_key: str
    slug: str
    project: str
    confidentiality: str
    episodes: list[HarvestedEpisode] = field(default_factory=list)

    def render_markdown(self) -> str:
        """Render the card as review-queue markdown with a human-gate frontmatter."""
        ordered = sorted(
            self.episodes, key=lambda e: (e.occurred_at or "", e.natural_key)
        )
        lines = [
            "---",
            f"story_key: {self.story_key}",
            f"project: {self.project}",
            f"confidentiality: {self.confidentiality}",
            "published: false  # human gate (DF-008): nothing publishes unattended",
            f"source: {FLYWHEEL_SOURCE}",
            f"episode_count: {len(ordered)}",
            "---",
            "",
            f"# Story: {self.story_key}",
            "",
            f"_Draft story card — pending human review (DF-008 human gate). "
            f"Confidentiality: **{self.confidentiality}**._",
            "",
            "## Timeline",
            "",
        ]
        for ep in ordered:
            when = ep.occurred_at or "(undated)"
            lines.append(f"- {when} · **{ep.payload_type}** — {_episode_summary(ep)}")
        lines.append("")
        return "\n".join(lines)


@dataclass
class HarvestResult:
    """The two DF-008-split outputs of a harvest pass."""

    dataset_rows: list[dict[str, Any]] = field(default_factory=list)
    story_cards: list[StoryCard] = field(default_factory=list)


def _confidentiality(project: str, public_projects: set[str]) -> str:
    """Confidentiality of a project's material (DF-008 — default confidential)."""
    return PUBLIC if project in public_projects else CONFIDENTIAL


def _slug(value: str) -> str:
    """A filesystem-safe slug for a story key."""
    return norm(value)[:120] or "unkeyed"


def _episode_summary(ep: HarvestedEpisode) -> str:
    """A one-line human summary of an episode for the story timeline."""
    p = ep.payload
    # Prefer the most telling status-like field per known type; fall back to identifier.
    for key_field in ("survival_state", "terminal_state", "decision", "verdict", "status"):
        value = p.get(key_field)
        if value:
            return f"{key_field.replace('_', ' ')}: {value}"
    return ep.identifier or ep.natural_key


def _flywheel_metadata(
    ep: HarvestedEpisode, public_projects: set[str], **extra: Any
) -> dict[str, Any]:
    """Build the flywheel provenance block carried on every dataset row."""
    meta: dict[str, Any] = {
        "source": FLYWHEEL_SOURCE,
        "layer": "behaviour",
        "turns": 2,
        "flywheel": {
            "episode_type": ep.payload_type,
            "natural_key": ep.natural_key,
            "project": ep.project,
            "source_ref": ep.source_ref,
            "occurred_at": ep.occurred_at,
            "confidentiality": _confidentiality(ep.project, public_projects),
        },
    }
    meta.update(extra)
    return meta


def _row(
    ep: HarvestedEpisode,
    user: str,
    assistant: str,
    public_projects: set[str],
    *,
    dimension: str,
    **extra_meta: Any,
) -> dict[str, Any]:
    """Assemble one ShareGPT flywheel dataset row."""
    return {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "metadata": _flywheel_metadata(
            ep, public_projects, dimension=dimension, **extra_meta
        ),
    }


def _extract_build_outcome(
    ep: HarvestedEpisode, public_projects: set[str]
) -> list[dict[str, Any]]:
    """A build retro carrying lessons/approach → one lesson row."""
    lessons = ep.payload.get("lessons")
    approach = ep.payload.get("approach")
    if not (lessons or approach):
        return []
    task = ep.payload.get("task_id") or ep.identifier
    status = ep.payload.get("status", "unknown")
    duration = ep.payload.get("duration_seconds")
    user = (
        f"A build for '{task}' finished with status '{status}'"
        + (f" in {duration}s" if duration is not None else "")
        + ". What are the lessons and the approach worth carrying forward?"
    )
    parts = []
    if lessons:
        parts.append(f"Lessons: {lessons}")
    if approach:
        parts.append(f"Approach: {approach}")
    return [
        _row(
            ep,
            user,
            "\n\n".join(parts),
            public_projects,
            dimension="build-retro",
        )
    ]


def _extract_planning_outcome(
    ep: HarvestedEpisode, public_projects: set[str]
) -> list[dict[str, Any]]:
    """Each non-accepted assumption with a contrastive delta → a refinement row.

    Forward-ready: ``planning_outcome`` has no wired producer yet (contract §5), so this
    extractor is dormant until Mode P emits rows — but the preference-pair intent lives
    here so no schema work is needed when it lands.
    """
    rows: list[dict[str, Any]] = []
    for assumption in ep.payload.get("assumptions", []):
        disposition = assumption.get("disposition")
        if disposition not in {"modified", "rejected", "deferred"}:
            continue
        delta = assumption.get("edit_delta")
        text = assumption.get("text") or assumption.get("assumption_id", "an assumption")
        if not (delta or text):
            continue
        user = f"Refine this planning assumption: {text}"
        assistant = delta or f"Disposition: {disposition} (see trace for the full edit)."
        rows.append(
            _row(
                ep,
                user,
                assistant,
                public_projects,
                dimension="assumption-refinement",
                disposition=disposition,
            )
        )
    return rows


#: Dataset-row extractors keyed by payload_type. Types without an extractor contribute to
#: story cards but produce no dataset rows (we do not manufacture low-signal rows).
DATASET_EXTRACTORS: dict[
    str, Callable[[HarvestedEpisode, set[str]], list[dict[str, Any]]]
] = {
    "build_outcome": _extract_build_outcome,
    "planning_outcome": _extract_planning_outcome,
}


def harvest(
    episodes: Iterable[HarvestedEpisode],
    *,
    public_projects: set[str] | None = None,
) -> HarvestResult:
    """Harvest episodes into flywheel dataset rows + draft story cards (pure).

    Args:
        episodes: Materialized episode records from the durable store.
        public_projects: Projects whose story cards are non-confidential; every other
            project's material is marked confidential (DF-008).

    Returns:
        A ``HarvestResult`` with dataset rows and one story card per distinct story.
    """
    public = public_projects or set()
    result = HarvestResult()

    # Preserve first-seen order for deterministic output.
    cards: OrderedDict[str, StoryCard] = OrderedDict()

    for ep in episodes:
        extractor = DATASET_EXTRACTORS.get(ep.payload_type)
        if extractor is not None:
            result.dataset_rows.extend(extractor(ep, public))

        story_key = ep.story_key()
        card = cards.get(story_key)
        if card is None:
            card = StoryCard(
                story_key=story_key,
                slug=_slug(story_key),
                project=ep.project,
                confidentiality=_confidentiality(ep.project, public),
            )
            cards[story_key] = card
        card.episodes.append(ep)
        # A story spanning any confidential project stays confidential (safe default).
        if _confidentiality(ep.project, public) == CONFIDENTIAL:
            card.confidentiality = CONFIDENTIAL

    result.story_cards = list(cards.values())
    return result
