"""Payload dispatch registry for typed payload serialization and round-trip.

Maps canonical payload_type names to model classes (bijection).
Supports name→model lookup, model→name reverse lookup, and serialize→rebuild round trip.

Producer: TASK-TPR-003
Consumer: FEAT-MEM-03 (deterministic writer), FEAT-MEM-04 (relay consumer)
"""

from __future__ import annotations

from fleet_memory.errors import UnknownPayloadTypeError
from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.models import (
    ADRPayload,
    BuildOutcomePayload,
    DocumentPayload,
    PatternPayload,
    ReviewReportPayload,
    SeedModulePayload,
    WarningPayload,
)

# Bijective registry: each canonical payload_type name maps to exactly one model class
PAYLOAD_REGISTRY: dict[str, type[BasePayload]] = {
    "adr": ADRPayload,
    "review_report": ReviewReportPayload,
    "build_outcome": BuildOutcomePayload,
    "pattern": PatternPayload,
    "warning": WarningPayload,
    "seed_module": SeedModulePayload,
    "document": DocumentPayload,
}

# Reverse lookup cache: model class → canonical type name
_MODEL_TO_TYPE: dict[type[BasePayload], str] = {
    model: name for name, model in PAYLOAD_REGISTRY.items()
}

# ---------------------------------------------------------------------------
# Backward-edge episode types — AUTHORED but NOT YET REGISTERED (contract §0/§5)
# ---------------------------------------------------------------------------
# The six backward-edge payload classes (payloads/backward_edge.py) are WS4-S7's
# deliverable, but the landing discipline is binding: a type joins PAYLOAD_REGISTRY ONLY
# in the window its producer is wired and emitting real episodes. Registering a type
# without a live producer is the ReviewReportPayload mistake (defined 2026-07-03, zero
# rows ever produced) — the relay would then accept a type nothing writes.
#
# As of authoring, none of the six producers are live:
#   - planning_outcome  → forge Mode-P terminal path   (waits on WS1-E forge wiring)
#   - approval_decision → forge gate path              (waits on WS1-E forge wiring)
#   - spec_survival     → forge (sole writer, §4.6)    (waits on WS1-E forge wiring)
#   - deploy_record     → forge DEPLOY stage (WS2 B8)  (INERT behind deploy.enabled=False)
#   - live_verdict      → forge LIVE_GATE stage (B8)   (INERT behind deploy.enabled=False)
#   - grading_outcome   → fleet-evals harness (WS4-S4) (producer unbuilt)
#
# To register a type when its producer lands: import its class into `models`-style scope
# and add ONE entry to PAYLOAD_REGISTRY above, in the same window the producer merges.
# tests/unit/test_backward_edge_payloads.py guards that this stays empty of unproduced
# types. The mapping below is DOCUMENTARY provenance only — it is not a registry.
_BACKWARD_EDGE_PRODUCER_GATES: dict[str, str] = {
    "planning_outcome": "forge Mode-P terminal path (WS1-E forge wiring)",
    "approval_decision": "forge gate path (WS1-E forge wiring)",
    "spec_survival": "forge sole writer (WS1-E forge wiring)",
    "deploy_record": "forge DEPLOY stage (WS2 B8; deploy.enabled=False → INERT)",
    "live_verdict": "forge LIVE_GATE stage (WS2 B8; deploy.enabled=False → INERT)",
    "grading_outcome": "fleet-evals harness (WS4-S4; producer unbuilt)",
}


def get_model_for_type(payload_type: str) -> type[BasePayload]:
    """Resolve payload_type name to model class.

    Args:
        payload_type: Canonical type name (case-sensitive)

    Returns:
        The model class for this payload type

    Raises:
        UnknownPayloadTypeError: If payload_type is not registered (ASSUM-010)
    """
    if payload_type not in PAYLOAD_REGISTRY:
        raise UnknownPayloadTypeError(payload_type)
    return PAYLOAD_REGISTRY[payload_type]


def get_type_for_model(model: type[BasePayload]) -> str:
    """Reverse lookup: model class to canonical type name.

    Args:
        model: A payload model class

    Returns:
        The canonical payload_type name

    Raises:
        ValueError: If model is not registered
    """
    if model not in _MODEL_TO_TYPE:
        raise ValueError(f"Model {model} is not registered in PAYLOAD_REGISTRY")
    return _MODEL_TO_TYPE[model]
