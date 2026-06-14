"""Unit tests for backfill review gate.

Tests the operator-controlled review marker pattern:
- Reviewed backfill publishes through TASK-RIP-002 publisher
- Unreviewed backfill is gated (not published)
- Self-asserted review without operator marker is gated
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fleet_memory.payloads.models import ADRPayload
from fleet_memory.reindex.backfill import (
    has_review_marker,
    process_backfill_payload,
)

if TYPE_CHECKING:
    from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_has_review_marker_present(tmp_path: Path) -> None:
    """Review marker file exists next to payload."""
    payload_path = tmp_path / "payload.json"
    marker_path = tmp_path / "payload.json.reviewed"

    payload_path.write_text("{}")
    marker_path.touch()

    assert has_review_marker(payload_path) is True


@pytest.mark.asyncio
async def test_has_review_marker_absent(tmp_path: Path) -> None:
    """Review marker file does not exist."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}")

    assert has_review_marker(payload_path) is False


@pytest.mark.asyncio
async def test_reviewed_payload_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Payload with review marker is published through TASK-RIP-002 publisher.

    Acceptance criteria:
    - AC: Staged payload WITH operator review marker is published
    - AC: Reviewed backfill publishes via same publisher (no second write path)
    """
    # Create valid ADR payload
    payload_data = {
        "project": "test_project",
        "identifier": "ADR_001",
        "decision": "Use microservices architecture for scalability",
        "status": "accepted",
        "source_ref": "backfill/staging/adr/ADR_001.json",
    }

    payload_path = tmp_path / "ADR_001.json"
    payload_path.write_text(json.dumps(payload_data))

    # Create review marker
    marker_path = tmp_path / "ADR_001.json.reviewed"
    marker_path.touch()

    # Mock the publisher from TASK-RIP-002
    publish_called = False
    published_payload = None

    async def mock_publish(payload):
        nonlocal publish_called, published_payload
        publish_called = True
        published_payload = payload

    # Patch the publish_episode function
    import fleet_memory.reindex.backfill as backfill_module

    monkeypatch.setattr(backfill_module, "publish_episode", mock_publish)

    # Process the backfill payload
    await process_backfill_payload(payload_path)

    # Verify publisher was called
    assert publish_called, "publish_episode should be called for reviewed payload"
    assert published_payload is not None
    assert isinstance(published_payload, ADRPayload)
    assert published_payload.identifier == "ADR_001"


@pytest.mark.asyncio
async def test_unreviewed_payload_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Payload without review marker is NOT published.

    Acceptance criteria:
    - AC: Staged payload WITHOUT review marker is not published
    """
    # Create valid ADR payload
    payload_data = {
        "project": "test_project",
        "identifier": "ADR_002",
        "decision": "Use PostgreSQL for data persistence",
        "status": "accepted",
        "source_ref": "backfill/staging/adr/ADR_002.json",
    }

    payload_path = tmp_path / "ADR_002.json"
    payload_path.write_text(json.dumps(payload_data))

    # NO review marker created

    # Mock the publisher
    publish_called = False

    async def mock_publish(payload):
        nonlocal publish_called
        publish_called = True

    import fleet_memory.reindex.backfill as backfill_module

    monkeypatch.setattr(backfill_module, "publish_episode", mock_publish)

    # Process the backfill payload
    await process_backfill_payload(payload_path)

    # Verify publisher was NOT called
    assert not publish_called, "publish_episode should NOT be called without marker"


@pytest.mark.asyncio
async def test_self_asserted_review_without_marker_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Payload claiming review in content but without marker is NOT published.

    Acceptance criteria:
    - AC: Payload whose content claims review but lacks operator marker is NOT published

    Security invariant: Only the filesystem marker grants review status, never
    payload content. This makes self-granting review structurally impossible.
    """
    # Create payload that CLAIMS to be reviewed in its content
    payload_data = {
        "project": "test_project",
        "identifier": "ADR_003",
        "decision": "Use event sourcing pattern",
        "status": "accepted",
        "source_ref": "backfill/staging/adr/ADR_003.json",
        "reviewed": True,  # Self-assertion in content
        "review_status": "approved",  # Another self-assertion
    }

    payload_path = tmp_path / "ADR_003.json"
    payload_path.write_text(json.dumps(payload_data))

    # NO review marker created (despite content claiming review)

    # Mock the publisher
    publish_called = False

    async def mock_publish(payload):
        nonlocal publish_called
        publish_called = True

    import fleet_memory.reindex.backfill as backfill_module

    monkeypatch.setattr(backfill_module, "publish_episode", mock_publish)

    # Process the backfill payload
    await process_backfill_payload(payload_path)

    # Verify publisher was NOT called (self-assertion ignored)
    assert (
        not publish_called
    ), "publish_episode should NOT be called even if payload claims review"


@pytest.mark.seam
@pytest.mark.integration_contract("memory_episode_routing")
async def test_reviewed_backfill_uses_same_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewed backfill publishes byte-identically to deterministic re-index.

    Contract: content_format == 'json' + payload_type set, via the SAME
    publisher (TASK-RIP-002) — no second write path.
    Producer: TASK-RIP-002

    This is the seam test from the task file.
    """
    # Create valid ADR payload
    payload_data = {
        "project": "test_project",
        "identifier": "ADR_SEAM",
        "decision": "Implement clean architecture boundaries",
        "status": "accepted",
        "source_ref": "backfill/staging/adr/ADR_SEAM.json",
    }

    payload_path = tmp_path / "ADR_SEAM.json"
    payload_path.write_text(json.dumps(payload_data))

    # Create review marker
    marker_path = tmp_path / "ADR_SEAM.json.reviewed"
    marker_path.touch()

    # Capture what would be published to broker
    published_episode = None

    async def mock_broker_publish(episode_data, subject):
        nonlocal published_episode
        published_episode = episode_data

    # Mock broker.publish (the actual NATS publish from TASK-RIP-002)
    from fleet_memory import app

    monkeypatch.setattr(app.broker, "publish", mock_broker_publish)

    # Process through the real backfill path
    await process_backfill_payload(payload_path)

    # Verify the episode matches the contract
    assert published_episode is not None, "Episode should be published"
    assert published_episode["content_format"] == "json"
    assert published_episode["payload_type"], "payload_type must be set"
    assert published_episode["payload_type"] == "adr"
