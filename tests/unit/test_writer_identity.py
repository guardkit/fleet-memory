"""Unit tests for record identity and content-hash helpers.

Tests cover:
- UUIDv5 determinism and stability
- Single application-wide namespace constant
- Natural key segment uniqueness
- Content hash semantic stability (version exclusion)
- Content hash sensitivity to semantic changes
- Pure function verification (no I/O)
"""

from __future__ import annotations

import uuid

import pytest

from fleet_memory.payloads.base import BasePayload
from fleet_memory.writer.identity import (
    FLEET_MEMORY_NAMESPACE,
    content_hash,
    record_identity,
)


# Test fixtures using BasePayload directly
@pytest.fixture
def base_payload() -> BasePayload:
    """Create a minimal BasePayload for testing."""
    return BasePayload(
        project="test_project",
        identifier="test_id_001",
        source_ref="test_source",
        version=1,
    )


@pytest.fixture
def base_payload_v2(base_payload: BasePayload) -> BasePayload:
    """Same payload with different version."""
    return BasePayload(
        project=base_payload.project,
        identifier=base_payload.identifier,
        source_ref=base_payload.source_ref,
        version=2,
    )


@pytest.fixture
def different_payload() -> BasePayload:
    """Payload with different semantic content."""
    return BasePayload(
        project="other_project",
        identifier="other_id_002",
        source_ref="other_source",
        version=1,
    )


class TestRecordIdentity:
    """Test record_identity function (AC-001, AC-002, AC-003)."""

    def test_returns_uuid5(self) -> None:
        """AC-001: record_identity returns a UUIDv5."""
        natural_key = "base:test_project:test_id_001"
        result = record_identity(natural_key)

        assert isinstance(result, uuid.UUID)
        assert result.version == 5

    def test_same_key_yields_identical_uuid(self) -> None:
        """AC-001: Same natural key yields byte-identical UUID on repeated calls."""
        natural_key = "base:test_project:test_id_001"

        uuid1 = record_identity(natural_key)
        uuid2 = record_identity(natural_key)
        uuid3 = record_identity(natural_key)

        assert uuid1 == uuid2
        assert uuid2 == uuid3
        # Verify byte-level identity
        assert uuid1.bytes == uuid2.bytes

    def test_uses_single_namespace_constant(self) -> None:
        """AC-002: Uses a single module-level namespace constant."""
        # Verify the namespace constant exists and is a UUID
        assert isinstance(FLEET_MEMORY_NAMESPACE, uuid.UUID)

        # Verify record_identity uses this namespace by manually computing
        natural_key = "base:test_project:test_id_001"
        expected = uuid.uuid5(FLEET_MEMORY_NAMESPACE, natural_key)
        actual = record_identity(natural_key)

        assert actual == expected

    def test_same_segments_yield_same_identity(
        self, base_payload: BasePayload
    ) -> None:
        """AC-003: Same payload_type/project/identifier → same identity."""
        # Create two separate calls with the same natural key
        uuid1 = record_identity(base_payload.natural_key)
        uuid2 = record_identity(base_payload.natural_key)

        assert uuid1 == uuid2

    def test_different_project_yields_different_identity(self) -> None:
        """AC-003: Different project segment → different identity."""
        key1 = "base:project_a:test_id"
        key2 = "base:project_b:test_id"

        uuid1 = record_identity(key1)
        uuid2 = record_identity(key2)

        assert uuid1 != uuid2

    def test_different_identifier_yields_different_identity(self) -> None:
        """AC-003: Different identifier segment → different identity."""
        key1 = "base:test_project:id_001"
        key2 = "base:test_project:id_002"

        uuid1 = record_identity(key1)
        uuid2 = record_identity(key2)

        assert uuid1 != uuid2

    def test_different_payload_type_yields_different_identity(self) -> None:
        """AC-003: Different payload_type segment → different identity."""
        key1 = "adr:test_project:test_id"
        key2 = "epic:test_project:test_id"

        uuid1 = record_identity(key1)
        uuid2 = record_identity(key2)

        assert uuid1 != uuid2


class TestContentHash:
    """Test content_hash function (AC-004, AC-005)."""

    def test_version_change_does_not_affect_hash(
        self, base_payload: BasePayload, base_payload_v2: BasePayload
    ) -> None:
        """AC-004: Same semantic content but different version → identical hash."""
        hash1 = content_hash(base_payload)
        hash2 = content_hash(base_payload_v2)

        assert hash1 == hash2

    def test_semantic_content_change_affects_hash(
        self, base_payload: BasePayload, different_payload: BasePayload
    ) -> None:
        """AC-005: Different semantic content → different hash."""
        hash1 = content_hash(base_payload)
        hash2 = content_hash(different_payload)

        assert hash1 != hash2

    def test_single_character_change_affects_hash(self) -> None:
        """AC-005: Single-character change in semantic content → different hash."""
        payload1 = BasePayload(
            project="test_project",
            identifier="test_id_001",
            source_ref="source_a",
            version=1,
        )
        payload2 = BasePayload(
            project="test_project",
            identifier="test_id_001",
            source_ref="source_b",  # Single character change
            version=1,
        )

        hash1 = content_hash(payload1)
        hash2 = content_hash(payload2)

        assert hash1 != hash2

    def test_domain_tags_affect_hash(self) -> None:
        """AC-005: Domain tags are semantic content."""
        payload1 = BasePayload(
            project="test_project",
            identifier="test_id_001",
            source_ref="test_source",
            domain_tags=["tag1", "tag2"],
            version=1,
        )
        payload2 = BasePayload(
            project="test_project",
            identifier="test_id_001",
            source_ref="test_source",
            domain_tags=["tag1", "tag3"],  # Different tag
            version=1,
        )

        hash1 = content_hash(payload1)
        hash2 = content_hash(payload2)

        assert hash1 != hash2

    def test_supersedes_affect_hash(self) -> None:
        """AC-005: Supersedes list is semantic content."""
        payload1 = BasePayload(
            project="test_project",
            identifier="test_id_001",
            source_ref="test_source",
            supersedes=["base:old_proj:old_id"],
            version=1,
        )
        payload2 = BasePayload(
            project="test_project",
            identifier="test_id_001",
            source_ref="test_source",
            supersedes=[],  # No supersedes
            version=1,
        )

        hash1 = content_hash(payload1)
        hash2 = content_hash(payload2)

        assert hash1 != hash2

    def test_hash_stability_across_calls(self, base_payload: BasePayload) -> None:
        """Content hash is deterministic across multiple calls."""
        hash1 = content_hash(base_payload)
        hash2 = content_hash(base_payload)
        hash3 = content_hash(base_payload)

        assert hash1 == hash2 == hash3


class TestPurityConstraints:
    """Test that both functions are pure (AC-006)."""

    def test_no_io_imports(self) -> None:
        """AC-006: Verify module doesn't import I/O libraries by inspection."""
        # This test verifies by inspection - the imports should be minimal
        # We test this by importing the module and checking what's available
        import fleet_memory.writer.identity as identity_module

        # Module should not have httpx, settings, store, or LLM imports
        module_names = dir(identity_module)

        # These should NOT be present
        forbidden = ["httpx", "Settings", "Store", "openai", "anthropic"]
        for forbidden_name in forbidden:
            assert forbidden_name not in module_names, (
                f"Found forbidden import '{forbidden_name}' in identity module"
            )

        # These SHOULD be present (our public API)
        assert "record_identity" in module_names
        assert "content_hash" in module_names
        assert "FLEET_MEMORY_NAMESPACE" in module_names

    def test_record_identity_is_pure(self) -> None:
        """AC-006: record_identity has no side effects."""
        natural_key = "base:test_project:test_id"

        # Call multiple times - if it's pure, results should be identical
        results = [record_identity(natural_key) for _ in range(10)]

        # All results should be identical
        assert len(set(results)) == 1

    def test_content_hash_is_pure(self, base_payload: BasePayload) -> None:
        """AC-006: content_hash has no side effects."""
        # Call multiple times - if it's pure, results should be identical
        results = [content_hash(base_payload) for _ in range(10)]

        # All results should be identical
        assert len(set(results)) == 1
