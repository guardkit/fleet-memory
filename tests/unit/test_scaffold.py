"""Test basic package scaffolding and imports."""


def test_package_imports():
    """Test that the fleet_memory package can be imported."""
    import fleet_memory

    assert hasattr(fleet_memory, "__version__")
    assert fleet_memory.__version__ == "0.1.0"


def test_langgraph_store_import():
    """Test that AsyncPostgresStore from langgraph is available."""
    from langgraph.store.postgres.aio import AsyncPostgresStore

    assert AsyncPostgresStore is not None
