"""Concrete payload type models for fleet-memory typed payload registry.

Implements seven canonical payload types that subclass BasePayload:
adr, review_report, build_outcome, pattern, warning, seed_module, document.

Each type declares its canonical payload_type and type-specific required fields.
Shared conventions (identifiers, supersession, domain tags) are inherited from BasePayload.
"""

from __future__ import annotations

from typing import ClassVar

from fleet_memory.payloads.base import BasePayload


class ADRPayload(BasePayload):
    """Architecture Decision Record payload.

    Tracks architectural decisions with decision text and status.
    """

    payload_type: ClassVar[str] = "adr"

    decision: str  # The architectural decision being documented
    status: str  # e.g., "proposed", "accepted", "deprecated", "superseded"


class ReviewReportPayload(BasePayload):
    """Code review or audit report payload.

    Requires a verdict field (e.g., "approved", "rejected", "needs_changes").
    """

    payload_type: ClassVar[str] = "review_report"

    verdict: str  # Required: the review outcome


class BuildOutcomePayload(BasePayload):
    """Build or CI pipeline outcome payload.

    Tracks build status, duration, and optional task context (task_id, lessons, approach).
    Extended fields (task_id, lessons, approach) are embedded for retrieval when provided.
    """

    payload_type: ClassVar[str] = "build_outcome"

    status: str  # e.g., "success", "failure", "timeout"
    duration_seconds: int  # Build execution time
    task_id: str | None = None  # Optional: links outcome to its task/feature
    lessons: str | None = None  # Optional: lessons-learned prose (embedded for retrieval)
    approach: str | None = None  # Optional: approach/methodology prose (embedded for retrieval)


class PatternPayload(BasePayload):
    """Design pattern or architectural pattern payload.

    Documents patterns with name and category.
    """

    payload_type: ClassVar[str] = "pattern"

    pattern_name: str  # e.g., "Singleton", "Factory", "Observer"
    category: str  # e.g., "creational", "structural", "behavioral"


class WarningPayload(BasePayload):
    """Warning or alert payload.

    Tracks warnings with severity and message.
    """

    payload_type: ClassVar[str] = "warning"

    severity: str  # e.g., "low", "medium", "high", "critical"
    message: str  # Human-readable warning description


class SeedModulePayload(BasePayload):
    """Seed module or bootstrap component payload.

    Tracks foundational modules with their path.
    """

    payload_type: ClassVar[str] = "seed_module"

    module_path: str  # Path to the module (e.g., "src/auth", "lib/core")


class DocumentPayload(BasePayload):
    """Generic document payload (catch-all type).

    Carries an optional prose ``content`` body. When provided, the text is embedded
    for semantic retrieval AND the record still carries ``domain_tags`` for
    group-scoped reads — this lets unstructured document/knowledge prose (e.g. the
    Graphiti Episodic nodes migrated in FEAT-MEM-09) be both semantically searchable
    and category-scoped, which a plain markdown chunk (no tags) cannot be. When
    ``content`` is omitted the payload is metadata-only (back-compat). Mirrors
    ``BuildOutcomePayload``'s optional ``lessons``/``approach`` prose fields.

    Note (relay): ``BasePayload.model_config`` is ``extra="ignore"``, so a relay image
    built BEFORE this field will SILENTLY DROP ``content`` (not DLQ it). The relay must
    be rebuilt for ``content`` to be stored/embedded.
    """

    payload_type: ClassVar[str] = "document"

    content: str | None = None  # Optional prose body; embedded for retrieval when provided
