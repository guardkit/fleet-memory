"""Unit tests for store factory and namespace validation.

Tests store factory construction and namespace validation without database.
No __aenter__ calls in unit tier - factory construction only.
"""

from __future__ import annotations

import pytest

from fleet_memory.embed import make_fake_embed
from fleet_memory.errors import NamespaceValidationError
from fleet_memory.settings import Settings
from fleet_memory.store import async_store_context, validate_namespace


class TestNamespaceValidation:
    """Test namespace validation rules: underscores only, no hyphens."""

    @pytest.mark.parametrize(
        "namespace,should_pass",
        [
            # Valid namespaces (underscores only)
            (("fleet_memory", "fleet_memory", "adr"), True),
            (("fleet_memory", "my_project", "chunk"), True),
            (("simple",), True),
            (("a", "b", "c"), True),
            (("test_123", "data_v2"), True),
            (("project_2026", "module_1", "item_42"), True),
            # Invalid namespaces (hyphens or other invalid chars)
            (("fleet_memory", "my-project", "chunk"), False),
            (("fleet-memory",), False),
            (("project", "sub-module", "item"), False),
            (("UPPERCASE",), False),
            (("has spaces",), False),
            (("has.dots",), False),
            (("has/slash",), False),
            (("",), False),
            (("valid", ""), False),
        ],
    )
    def test_namespace_validation_table(
        self, namespace: tuple[str, ...], should_pass: bool
    ) -> None:
        """Verify namespace validation accepts underscores, rejects hyphens and other chars."""
        if should_pass:
            # Should not raise
            validate_namespace(namespace)
        else:
            # Should raise NamespaceValidationError
            with pytest.raises(NamespaceValidationError) as exc_info:
                validate_namespace(namespace)
            # Verify error message mentions underscores
            assert "underscores" in str(exc_info.value).lower()
            # Verify namespace is captured
            assert exc_info.value.namespace == namespace

    def test_hyphen_namespace_explicit(self) -> None:
        """Explicit test: namespace with hyphens raises NamespaceValidationError.

        BDD Scenario: "A namespace containing hyphens is rejected"
        """
        with pytest.raises(NamespaceValidationError) as exc_info:
            validate_namespace(("fleet_memory", "my-project", "chunk"))

        error = exc_info.value
        assert error.namespace == ("fleet_memory", "my-project", "chunk")
        assert "my-project" in error.invalid_parts
        assert "underscores" in str(error).lower()

    def test_valid_namespace_explicit(self) -> None:
        """Explicit test: valid namespace with underscores passes.

        From acceptance criteria: validate_namespace(("fleet_memory", "fleet_memory", "adr"))
        """
        # Should not raise
        validate_namespace(("fleet_memory", "fleet_memory", "adr"))


class TestStoreFactory:
    """Test async_store_context factory construction without entering context."""

    def test_factory_construction_with_fake_embed(self) -> None:
        """Verify factory constructs with fake embed callable, no database required.

        Unit tier: construct factory but never __aenter__ (no database).
        """
        settings = Settings(
            pg_dsn="postgresql://u:p@localhost:5499/db",
            embed_url="http://localhost:9000",
        )
        fake_embed = make_fake_embed(settings.embed_dims)

        # Construct context manager but do NOT enter it
        ctx = async_store_context(settings, embed_fn=fake_embed)

        # Verify it's an async context manager
        assert hasattr(ctx, "__aenter__")
        assert hasattr(ctx, "__aexit__")

    def test_factory_construction_without_embed_fn(self) -> None:
        """Verify factory constructs with embed_fn=None (real embed callable from settings)."""
        settings = Settings(
            pg_dsn="postgresql://u:p@localhost:5499/db",
            embed_url="http://localhost:9000",
        )

        # Construct context manager with None (should build real embed callable internally)
        ctx = async_store_context(settings, embed_fn=None)

        # Verify it's an async context manager
        assert hasattr(ctx, "__aenter__")
        assert hasattr(ctx, "__aexit__")


# Seam tests from task requirements


@pytest.mark.seam
@pytest.mark.integration_contract("FLEET_MEMORY_PG_DSN")
def test_pg_dsn_format_is_psycopg3_conninfo() -> None:
    """Verify the DSN is plain postgresql:// psycopg3 conninfo.

    Contract: plain postgresql:// — NO +asyncpg dialect suffix (psycopg3 driver).
    Producer: TASK-MEM-002
    """
    settings = Settings(
        pg_dsn="postgresql://u:p@localhost:5499/db",
        embed_url="http://localhost:9000",
    )
    dsn = str(settings.pg_dsn)
    assert dsn.startswith("postgresql://"), f"Expected plain postgresql:// conninfo, got: {dsn}"
    assert "+asyncpg" not in dsn, f"psycopg3 conninfo must not carry +asyncpg suffix: {dsn}"


@pytest.mark.seam
@pytest.mark.integration_contract("EMBED_CALLABLE")
async def test_embed_callable_returns_768_dim_vectors() -> None:
    """Verify the embed callable contract consumed by the store index config.

    Contract: async list[str] -> list[list[float]], exactly 768 floats per vector.
    Producer: TASK-MEM-003
    """
    embed = make_fake_embed(768)
    vectors = await embed(["one text", "two text"])
    assert len(vectors) == 2
    assert all(len(v) == 768 for v in vectors), "Every vector must be exactly 768 dims"
