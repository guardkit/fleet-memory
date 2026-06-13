"""Unit tests for memory_write_payload MCP tool.

Tests validation boundary, derived-identity ack, error handling, and graceful
degradation. Uses a fake DeterministicWriter to isolate tool logic.

Producer: TASK-MCP-004
"""

from __future__ import annotations

import pytest

from fleet_memory.mcp.degradation import ToolResult


@pytest.fixture
def fake_writer():
    """Fake writer that records calls for verification."""

    class FakeWriter:
        def __init__(self):
            self.writes = []
            self.should_raise = None

        async def write(self, payload):
            if self.should_raise:
                raise self.should_raise
            self.writes.append(payload)

    return FakeWriter()


@pytest.mark.asyncio
async def test_derived_identity_ack(fake_writer):
    """Tool returns derived identity (natural key) on successful write."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        "payload_type": "adr",
        "project": "my_project",
        "identifier": "ADR_001",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is False
    assert result.value == "adr:my_project:ADR_001"
    assert len(fake_writer.writes) == 1
    assert fake_writer.writes[0].natural_key == "adr:my_project:ADR_001"


@pytest.mark.asyncio
async def test_unknown_type_rejected(fake_writer):
    """Unknown payload type rejected with client error, nothing persisted."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        "payload_type": "meeting_notes",  # Not in registry
        "project": "my_project",
        "identifier": "NOTE_001",
        "source_ref": "github:org/repo@abc123",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert result.error_type == "client"
    assert "meeting_notes" in result.message
    assert "not recognised" in result.message.lower() or "unknown" in result.message.lower()
    assert len(fake_writer.writes) == 0  # Nothing persisted


@pytest.mark.asyncio
async def test_invalid_identifier_rejected(fake_writer):
    """Identifier with invalid characters (spaces) rejected, nothing persisted."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        "payload_type": "adr",
        "project": "my_project",
        "identifier": "ADR 001",  # Contains space - invalid
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert result.error_type == "client"
    assert "identifier" in result.message.lower()
    assert "invalid" in result.message.lower()
    assert len(fake_writer.writes) == 0


@pytest.mark.asyncio
async def test_missing_field_rejected(fake_writer):
    """Payload missing required field rejected with named field in error."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        "payload_type": "adr",
        # Missing "project" - required field
        "identifier": "ADR_001",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert result.error_type == "client"
    assert "project" in result.message.lower() or "required" in result.message.lower()
    assert len(fake_writer.writes) == 0


@pytest.mark.asyncio
async def test_untyped_rejected(fake_writer):
    """Untyped/free-form write (no payload_type) rejected."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        # No payload_type field - untyped
        "project": "my_project",
        "identifier": "FREEFORM_001",
        "source_ref": "github:org/repo@abc123",
        "content": "Some free-form content",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert result.error_type == "client"
    assert "payload_type" in result.message.lower() or "required" in result.message.lower()
    assert len(fake_writer.writes) == 0


@pytest.mark.asyncio
async def test_forged_identity_ignored(fake_writer):
    """Client-supplied stored_identity is ignored; server-derived key used."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        "payload_type": "adr",
        "project": "my_project",
        "identifier": "ADR_001",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
        "stored_identity": "forged:fake:key",  # Client trying to forge identity
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is False
    # Server-derived natural key is returned, not the forged one
    assert result.value == "adr:my_project:ADR_001"
    assert len(fake_writer.writes) == 1
    # Verify the payload sent to writer has the correct natural key
    assert fake_writer.writes[0].natural_key == "adr:my_project:ADR_001"


@pytest.mark.asyncio
async def test_idempotent_double_write(fake_writer):
    """Writing the same payload twice results in one record (idempotency)."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    payload_dict = {
        "payload_type": "adr",
        "project": "my_project",
        "identifier": "ADR_001",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
    }

    # First write
    result1 = await memory_write_payload(payload_dict, fake_writer)
    assert result1.is_error is False
    assert result1.value == "adr:my_project:ADR_001"

    # Second write (same payload)
    result2 = await memory_write_payload(payload_dict, fake_writer)
    assert result2.is_error is False
    assert result2.value == "adr:my_project:ADR_001"

    # Writer receives both calls (idempotency handled at writer level)
    assert len(fake_writer.writes) == 2
    assert fake_writer.writes[0].natural_key == fake_writer.writes[1].natural_key


@pytest.mark.asyncio
async def test_store_down_degrades(fake_writer):
    """When store raises TimeoutError, tool returns infrastructure error."""
    from fleet_memory.mcp.tools.write import memory_write_payload

    fake_writer.should_raise = TimeoutError("Connection timeout")

    payload_dict = {
        "payload_type": "adr",
        "project": "my_project",
        "identifier": "ADR_001",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert result.error_type == "infrastructure"
    assert "unavailable" in result.message.lower() or "timeout" in result.message.lower()


@pytest.mark.asyncio
async def test_embed_down_no_partial_write(fake_writer):
    """When embeddings unavailable, write rejected with no partial record."""
    from fleet_memory.errors import EmbedServiceError
    from fleet_memory.mcp.tools.write import memory_write_payload

    fake_writer.should_raise = EmbedServiceError("Embedding service unreachable")

    payload_dict = {
        "payload_type": "adr",
        "project": "my_project",
        "identifier": "ADR_001",
        "source_ref": "github:org/repo@abc123",
        "decision": "Use PostgreSQL for persistence",
        "status": "accepted",
    }

    result = await memory_write_payload(payload_dict, fake_writer)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert result.error_type == "infrastructure"
    assert "unavailable" in result.message.lower() or "temporarily" in result.message.lower()
    # Nothing persisted - writer was never called successfully
    assert len(fake_writer.writes) == 0
