"""Backfill processor with operator review gate.

Walks backfill/staging/ for Fable-authored payloads and publishes each ONLY when
an operator-controlled sidecar review marker exists. The review marker is a
filesystem artifact (.reviewed file) that cannot be self-granted by payload content.

Reviewed backfill reuses the same publisher (TASK-RIP-002) and relay path as
deterministic re-index — one write path, byte-identical.

Security model: The marker check is the gate's whole security. We read the marker
from the filesystem next to the payload, NEVER from inside the payload body. This
makes "a payload that claims it is reviewed" structurally unable to publish itself.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.reindex.publisher import publish_episode

if TYPE_CHECKING:
    from fleet_memory.payloads.base import BasePayload

logger = logging.getLogger(__name__)


def has_review_marker(payload_path: Path) -> bool:
    """Check if an operator review marker exists for a payload file.

    The review marker is a sidecar file with `.reviewed` suffix next to the payload.
    This is a filesystem-level gate that payload content cannot self-grant.

    Args:
        payload_path: Path to the payload JSON file

    Returns:
        True if the review marker file exists, False otherwise

    Examples:
        >>> has_review_marker(Path("backfill/staging/adr/ADR_001.json"))
        True  # if ADR_001.json.reviewed exists
        False  # if marker file does not exist
    """
    marker_path = payload_path.parent / f"{payload_path.name}.reviewed"
    return marker_path.exists()


async def process_backfill_payload(payload_path: Path) -> None:
    """Process a single backfill payload with operator review gate.

    Only publishes the payload if an operator review marker exists. The marker
    is a sidecar `.reviewed` file — git-trackable, per-payload, and impossible
    for a payload to self-grant.

    The payload is published through the same publisher (TASK-RIP-002) and relay
    path as deterministic re-index — no second write path.

    Args:
        payload_path: Path to the payload JSON file

    Raises:
        FileNotFoundError: If payload file does not exist
        json.JSONDecodeError: If payload is not valid JSON
        ValueError: If payload cannot be parsed by registry
    """
    # Check for operator review marker (ASSUM-003)
    if not has_review_marker(payload_path):
        logger.debug(
            f"Skipping {payload_path}: no operator review marker (gate enforced)"
        )
        return

    # Load payload content
    payload_content = json.loads(payload_path.read_text())

    # Infer payload type from content or filename
    # The registry will parse it based on payload_type field if present,
    # or we can infer from filename pattern (e.g., ADR_*.json -> adr)
    payload_type = payload_content.get("payload_type")

    if not payload_type:
        # Infer from filename if not in content
        # This is a simple heuristic - could be made more sophisticated
        filename = payload_path.stem
        if filename.startswith("ADR_"):
            payload_type = "adr"
        else:
            # Default or raise error
            raise ValueError(
                f"Cannot infer payload_type for {payload_path}: "
                f"no payload_type field and filename pattern not recognized"
            )
        # Add payload_type to content for registry
        payload_content["payload_type"] = payload_type

    # Get the model class for this payload type
    model_class = get_model_for_type(payload_type)

    # Parse and validate payload
    payload: BasePayload = model_class(**payload_content)

    # Publish through TASK-RIP-002 publisher (single write path, no duplication)
    await publish_episode(payload)

    logger.info(
        f"Published reviewed backfill payload: {payload.natural_key} "
        f"(type={payload.payload_type})"
    )
