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
