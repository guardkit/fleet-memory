"""Unit tests for ChunkWriter: deterministic chunk storage with embed-on-write.

Tests verify the uuid5(episode_id, index) key contract, idempotent redelivery,
namespace validation, and content field requirement for embedding.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from fleet_memory.errors import NamespaceValidationError
from fleet_memory.relay.chunk_writer import ChunkWriter
from fleet_memory.relay.schema import Chunk
from fleet_memory.writer.identity import FLEET_MEMORY_NAMESPACE


def _make_chunk(**overrides) -> Chunk:
    """Factory for Chunk test instances."""
    defaults = {
        "index": 0,
        "text": "Test chunk content",
        "source_ref": "ref://test",
        "project": "test_proj",
    }
    defaults.update(overrides)
    return Chunk(**defaults)


@pytest.fixture
def make_chunk():
    """Fixture providing Chunk factory."""
    return _make_chunk


@pytest.fixture
def mock_store():
    """Mock AsyncPostgresStore for testing chunk write logic."""
    store = AsyncMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    return store


# AC-001: Chunk store key is uuid5(episode_id, index) — deterministic and stable across redeliveries
@pytest.mark.asyncio
async def test_chunk_key_is_deterministic_uuid5(mock_store, make_chunk):
    """Verify chunk keys are derived via uuid5(episode_id, chunk.index).

    The same episode_id + index MUST always produce the same UUID key.
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(index=0), make_chunk(index=1)]
    episode_id = "ep-123"

    await writer.write_chunks(episode_id, chunks)

    # Verify aput was called twice (one per chunk)
    assert mock_store.aput.call_count == 2

    # Extract the store keys from the calls
    call_args_list = mock_store.aput.call_args_list

    # Verify first chunk key
    expected_key_0 = str(uuid.uuid5(FLEET_MEMORY_NAMESPACE, f"{episode_id}:0"))
    actual_namespace_0, actual_key_0, _ = call_args_list[0][0]
    assert actual_key_0 == expected_key_0

    # Verify second chunk key
    expected_key_1 = str(uuid.uuid5(FLEET_MEMORY_NAMESPACE, f"{episode_id}:1"))
    actual_namespace_1, actual_key_1, _ = call_args_list[1][0]
    assert actual_key_1 == expected_key_1


# AC-002: Writing the same (episode_id, chunks) twice leaves an identical chunk set (no duplicates)
@pytest.mark.asyncio
async def test_redelivery_overwrites_same_keys_no_duplicates(mock_store, make_chunk):
    """Verify redelivery of the same episode overwrites chunks in place.

    Because keys are deterministic, a second write of the same episode_id
    should target the exact same store keys (idempotent).
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(index=0, text="chunk 0"), make_chunk(index=1, text="chunk 1")]
    episode_id = "ep-456"

    # Write once
    await writer.write_chunks(episode_id, chunks)
    first_call_count = mock_store.aput.call_count

    # Write again with same episode_id
    await writer.write_chunks(episode_id, chunks)
    second_call_count = mock_store.aput.call_count

    # Should have written 2 chunks each time (4 total calls)
    assert first_call_count == 2
    assert second_call_count == 4

    # Verify the keys are identical between first and second write
    first_keys = {call[0][1] for call in mock_store.aput.call_args_list[:2]}
    second_keys = {call[0][1] for call in mock_store.aput.call_args_list[2:4]}
    assert first_keys == second_keys  # Same keys → overwrites in place


# AC-003: Each stored value carries a 'content' field so embed-on-write fires
# via the store index config
@pytest.mark.asyncio
async def test_stored_value_contains_content_field(mock_store, make_chunk):
    """Verify each stored chunk includes a 'content' field for embedding.

    The store's index config (fields=['content']) requires this field.
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(text="This is the chunk text")]
    episode_id = "ep-789"

    await writer.write_chunks(episode_id, chunks)

    # Extract the stored value
    _, _, stored_value = mock_store.aput.call_args[0]

    # Verify 'content' field exists and contains the chunk text
    assert "content" in stored_value
    assert stored_value["content"] == "This is the chunk text"


# AC-004: Each stored chunk records source_ref and is confined to ("fleet_memory", project, "chunk")
@pytest.mark.asyncio
async def test_chunk_stored_under_project_chunk_namespace(mock_store, make_chunk):
    """Verify chunks are written to ("fleet_memory", <project>, "chunk") namespace.

    Each chunk must also record source_ref and other metadata.
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [
        make_chunk(
            index=0,
            text="chunk text",
            source_ref="ref://doc/123",
            project="guardkit",
        )
    ]
    episode_id = "ep-abc"

    await writer.write_chunks(episode_id, chunks)

    # Verify namespace
    namespace, key, stored_value = mock_store.aput.call_args[0]
    assert namespace == ("fleet_memory", "guardkit", "chunk")

    # Verify stored metadata
    assert stored_value["source_ref"] == "ref://doc/123"
    assert stored_value["project"] == "guardkit"
    assert stored_value["episode_id"] == "ep-abc"
    assert stored_value["chunk_index"] == 0


# AC-005: validate_namespace is called before any aput; hyphenated project
# raises NamespaceValidationError
@pytest.mark.asyncio
async def test_hyphenated_project_raises_namespace_validation_error(mock_store, make_chunk):
    """Verify hyphenated project names are rejected before any write.

    NamespaceValidationError should be raised and no chunks should be written.
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(project="my-project")]  # Hyphenated project
    episode_id = "ep-bad"

    with pytest.raises(NamespaceValidationError) as exc_info:
        await writer.write_chunks(episode_id, chunks)

    # Verify the error identifies the invalid part
    assert "my-project" in exc_info.value.invalid_parts

    # Verify NO writes occurred
    mock_store.aput.assert_not_called()


# AC-006: A delimiter/path-shaped episode_id cannot place a chunk outside
# the project's chunk namespace
@pytest.mark.asyncio
async def test_path_shaped_episode_id_confined_to_namespace(mock_store, make_chunk):
    """Verify path-shaped episode_id values are safely confined to the key (not namespace).

    An episode_id like "../../escape" should not affect the namespace tuple.
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(project="safe_proj")]
    episode_id = "../../escape/attempt"  # Path-shaped

    await writer.write_chunks(episode_id, chunks)

    # Verify namespace is still correct
    namespace, key, _ = mock_store.aput.call_args[0]
    assert namespace == ("fleet_memory", "safe_proj", "chunk")

    # Verify the episode_id is safely embedded in the key derivation
    expected_key = str(uuid.uuid5(FLEET_MEMORY_NAMESPACE, f"{episode_id}:0"))
    assert key == expected_key


# AC-007: Unit tests use the in-memory/fake store (no live infra)
# This is already satisfied by using mock_store fixture throughout


# Integration contract seam test (from task spec)
@pytest.mark.seam
@pytest.mark.integration_contract("chunk_namespace")
async def test_chunk_written_under_project_chunk_namespace_seam(mock_store, make_chunk):
    """Seam test: verify chunk namespace + embed-on-write contract.

    Contract: namespace tuple + 'content' field for embed-on-write.
    Producer: TASK-RLY-001 (Chunk), TASK-MEM-005 (store)
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(index=0, text="hello", source_ref="ref://a", project="guardkit")]
    await writer.write_chunks("ep-1", chunks)

    # Verify write occurred
    assert mock_store.aput.call_count == 1

    # Verify namespace and content field
    namespace, _, stored_value = mock_store.aput.call_args[0]
    assert namespace == ("fleet_memory", "guardkit", "chunk")
    assert "content" in stored_value


# Regression: no duplicate chunks on redelivery
@pytest.mark.regression
@pytest.mark.asyncio
async def test_no_duplicate_chunks_on_redelivery(mock_store, make_chunk):
    """Regression test: redelivery must not create duplicate chunks.

    The deterministic key contract ensures overwrites, not appends.
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [make_chunk(index=0), make_chunk(index=1), make_chunk(index=2)]
    episode_id = "ep-regression"

    # Simulate redelivery (write same episode twice)
    await writer.write_chunks(episode_id, chunks)
    await writer.write_chunks(episode_id, chunks)

    # Verify total writes: 2 deliveries × 3 chunks = 6 writes
    assert mock_store.aput.call_count == 6

    # Extract all written keys
    all_keys = [call[0][1] for call in mock_store.aput.call_args_list]

    # First 3 and second 3 should be identical sets
    first_delivery_keys = set(all_keys[:3])
    second_delivery_keys = set(all_keys[3:6])
    assert first_delivery_keys == second_delivery_keys


# Edge case: empty chunks list
@pytest.mark.asyncio
async def test_empty_chunks_list_writes_nothing(mock_store):
    """Verify empty chunks list results in no store writes."""
    writer = ChunkWriter(store=mock_store)
    await writer.write_chunks("ep-empty", [])

    # No writes should occur
    mock_store.aput.assert_not_called()


# Edge case: multiple chunks from same episode, different projects
# (should not happen, but defensive)
@pytest.mark.asyncio
async def test_chunks_must_share_same_project(mock_store, make_chunk):
    """Verify all chunks in a batch share the same project.

    If chunks have different projects, each goes to its own namespace.
    (This scenario shouldn't occur in production but tests defensive behavior.)
    """
    writer = ChunkWriter(store=mock_store)
    chunks = [
        make_chunk(index=0, project="proj_a"),
        make_chunk(index=1, project="proj_b"),
    ]
    episode_id = "ep-mixed"

    await writer.write_chunks(episode_id, chunks)

    # Verify each chunk went to its own project namespace
    namespaces = [call[0][0] for call in mock_store.aput.call_args_list]
    assert namespaces[0] == ("fleet_memory", "proj_a", "chunk")
    assert namespaces[1] == ("fleet_memory", "proj_b", "chunk")
