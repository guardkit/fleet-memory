"""Typed payload models for fleet-memory.

This package defines the BasePayload contract and concrete payload types
for the typed-payload-registry feature (FEAT-MEM-02).
"""

from __future__ import annotations

from fleet_memory.payloads.base import (
    BasePayload,
    IdentifierValidationError,
    SupersessionValidationError,
)

__all__ = [
    "BasePayload",
    "IdentifierValidationError",
    "SupersessionValidationError",
]
