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

    Tracks build status and duration.
    """

    payload_type: ClassVar[str] = "build_outcome"

    status: str  # e.g., "success", "failure", "timeout"
    duration_seconds: int  # Build execution time


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

    Accepts payloads with no type-specific fields beyond BasePayload requirements.
    This is the fallback type for content that doesn't fit other categories.
    """

    payload_type: ClassVar[str] = "document"

    # No type-specific fields - inherits only BasePayload fields
