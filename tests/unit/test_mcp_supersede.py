"""Unit tests for memory_supersede MCP tool.

Tests the supersede tool that declares supersession by validating inputs
at the boundary and dispatching to apply_supersessions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_store() -> AsyncMock:
    """Create a mock AsyncPostgresStore for testing."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_single_predecessor_accepted(mock_store: AsyncMock) -> None:
    """Single predecessor declaration is accepted and applied.

    When a single predecessor is provided, the tool should accept it
    and call apply_supersessions with the successor and predecessor list.
    """
    from unittest.mock import MagicMock

    from fleet_memory.mcp.tools.supersede import memory_supersede

    # Mock an existing record
    existing_record = MagicMock()
    existing_record.value = {"natural_key": "memory:project:old-doc"}
    mock_store.aget = AsyncMock(return_value=existing_record)
    mock_store.aput = AsyncMock()

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:new-doc",
        predecessor_keys=["memory:project:old-doc"],
    )

    assert result.is_error is False
    assert "marked 1 predecessor as superseded" in result.value.lower()


@pytest.mark.asyncio
async def test_multiple_predecessors_accepted(mock_store: AsyncMock) -> None:
    """Multiple predecessors are accepted and applied.

    When multiple predecessors are provided, all should be processed.
    """
    from unittest.mock import MagicMock

    from fleet_memory.mcp.tools.supersede import memory_supersede

    # Mock existing records for both predecessors
    existing_record_1 = MagicMock()
    existing_record_1.value = {"natural_key": "memory:project:old-doc-1"}
    existing_record_2 = MagicMock()
    existing_record_2.value = {"natural_key": "memory:project:old-doc-2"}

    mock_store.aget = AsyncMock(side_effect=[existing_record_1, existing_record_2])
    mock_store.aput = AsyncMock()

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:new-doc",
        predecessor_keys=["memory:project:old-doc-1", "memory:project:old-doc-2"],
    )

    assert result.is_error is False
    assert "marked 2 predecessors as superseded" in result.value.lower()


@pytest.mark.asyncio
async def test_empty_predecessor_list_rejected(mock_store: AsyncMock) -> None:
    """Empty predecessor list is rejected with specific error message.

    ASSUM-005: Empty list should be rejected at the tool boundary,
    not silently ignored.
    """
    from fleet_memory.mcp.tools.supersede import memory_supersede

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:new-doc",
        predecessor_keys=[],
    )

    assert result.is_error is True
    assert result.error_type == "client"
    assert "at least one predecessor is required" in result.message.lower()


@pytest.mark.asyncio
async def test_malformed_predecessor_rejected(mock_store: AsyncMock) -> None:
    """Malformed predecessor reference is rejected with validation error.

    A key that doesn't match type:project:identifier format should be
    rejected with a clear message, and no supersession applied.
    """
    from fleet_memory.mcp.tools.supersede import memory_supersede

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:new-doc",
        predecessor_keys=["not-a-valid-key"],
    )

    assert result.is_error is True
    assert result.error_type == "client"
    assert "not a valid memory key" in result.message.lower()


@pytest.mark.asyncio
async def test_malformed_successor_rejected(mock_store: AsyncMock) -> None:
    """Malformed successor reference is rejected with validation error."""
    from fleet_memory.mcp.tools.supersede import memory_supersede

    result = await memory_supersede(
        store=mock_store,
        successor_key="invalid",
        predecessor_keys=["memory:project:old-doc"],
    )

    assert result.is_error is True
    assert result.error_type == "client"
    assert "not a valid memory key" in result.message.lower()


@pytest.mark.asyncio
async def test_self_supersession_rejected(mock_store: AsyncMock) -> None:
    """Memory superseding itself is rejected with specific error.

    A memory cannot supersede itself - this should be caught at the
    tool boundary before calling apply_supersessions.
    """
    from fleet_memory.mcp.tools.supersede import memory_supersede

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:doc",
        predecessor_keys=["memory:project:doc"],
    )

    assert result.is_error is True
    assert result.error_type == "client"
    assert "a memory cannot supersede itself" in result.message.lower()


@pytest.mark.asyncio
async def test_self_supersession_in_list_rejected(mock_store: AsyncMock) -> None:
    """Self-supersession rejected even when mixed with valid predecessors."""
    from fleet_memory.mcp.tools.supersede import memory_supersede

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:doc",
        predecessor_keys=["memory:project:other", "memory:project:doc"],
    )

    assert result.is_error is True
    assert result.error_type == "client"
    assert "a memory cannot supersede itself" in result.message.lower()


@pytest.mark.asyncio
async def test_store_timeout_degrades_gracefully(mock_store: AsyncMock) -> None:
    """When store raises TimeoutError, tool returns unavailable message.

    The tool should degrade gracefully via TASK-MCP-002 wrapper,
    returning infrastructure error instead of crashing the server.
    """
    from fleet_memory.mcp.tools.supersede import memory_supersede

    # Mock apply_supersessions to raise TimeoutError
    mock_store.aget = AsyncMock(side_effect=TimeoutError("Connection timeout"))

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:new-doc",
        predecessor_keys=["memory:project:old-doc"],
    )

    assert result.is_error is True
    assert result.error_type == "infrastructure"
    assert "memory store" in result.message.lower()


@pytest.mark.asyncio
async def test_forward_supersession_accepted(mock_store: AsyncMock) -> None:
    """Forward supersession (predecessor doesn't exist yet) is accepted.

    Declaring supersession of a not-yet-written predecessor should be
    accepted - the link will take effect once the predecessor is written.
    """
    from fleet_memory.mcp.tools.supersede import memory_supersede

    # Configure mock to simulate predecessor not existing
    mock_store.aget = AsyncMock(return_value=None)

    result = await memory_supersede(
        store=mock_store,
        successor_key="memory:project:new-doc",
        predecessor_keys=["memory:project:future-doc"],
    )

    assert result.is_error is False
    assert "marked 1 predecessor as superseded" in result.value.lower()


@pytest.mark.seam
@pytest.mark.integration_contract("apply_supersessions")
def test_apply_supersessions_contract() -> None:
    """Verify the supersession surface matches the contract the tool depends on.

    Contract: apply_supersessions(store, successor_natural_key, predecessor_natural_keys)
    is async; predecessor keys are type:project:identifier natural keys.
    Producer: FEAT-MEM-03 (fleet_memory.writer.supersession)
    """
    import inspect

    from fleet_memory.writer.supersession import apply_supersessions

    assert inspect.iscoroutinefunction(apply_supersessions)
    params = list(inspect.signature(apply_supersessions).parameters)
    assert params[:3] == ["store", "successor_natural_key", "predecessor_natural_keys"]
