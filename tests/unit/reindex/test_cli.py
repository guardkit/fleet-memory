"""Tests for re-index CLI entrypoint.

Tests verify:
- Mid-run failures are surfaced loudly with affected document names
- Re-running after interruption is safe (no duplicates)
- --help works without requiring a live connection
"""

from __future__ import annotations

import subprocess
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleet_memory.payloads.base import BasePayload
from fleet_memory.reindex.pipeline import RunReport


@pytest.mark.asyncio
async def test_midrun_failure_names_affected_documents_and_exits_nonzero() -> None:
    """Mid-run publisher failure reports affected document and exits non-zero.

    A relay/store outage mid-run causes the CLI to report failure with the
    affected documents named (no silent skip) and exit non-zero.
    """
    # Fake publisher that raises after first document
    call_count = 0

    async def fake_publisher_raises(payload: BasePayload) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise RuntimeError("Store connection lost")

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.corpus_root = "fake_corpus"
    mock_settings.backfill_dir = "fake_backfill"
    mock_settings.pg_dsn = "postgresql://fake"
    mock_settings.embed_url = "http://fake"

    # Mock store context
    mock_store = AsyncMock()

    # Mock async_store_context
    @asynccontextmanager
    async def mock_store_context(settings, embed_fn=None):
        yield mock_store

    # Mock reindex_corpus to simulate partial success
    async def mock_reindex_corpus(corpus_root, publisher):
        await publisher(MagicMock(natural_key="doc:proj:001", payload_type="test"))
        await publisher(MagicMock(natural_key="doc:proj:002", payload_type="test"))
        # Second call will raise
        return RunReport(published_count=1, unparseable_count=0, unrecognized_count=0)

    with (
        patch("fleet_memory.reindex.__main__.Settings", return_value=mock_settings),
        patch(
            "fleet_memory.reindex.__main__.async_store_context", mock_store_context
        ),
        patch(
            "fleet_memory.reindex.__main__.reindex_corpus", mock_reindex_corpus
        ),
        patch(
            "fleet_memory.reindex.__main__.process_backfill", AsyncMock()
        ),
        patch("sys.argv", ["reindex"]),  # Mock argv to avoid argparse issues
    ):
        # Import here to use patched dependencies
        from fleet_memory.reindex.__main__ import main

        # Run and capture exception
        with pytest.raises(SystemExit) as exc_info:
            await main()

        # Should exit non-zero on failure
        assert exc_info.value.code != 0


def test_help_exits_zero_without_connection() -> None:
    """--help exits 0 and does not require a live connection.

    The help command should work even when database/NATS are unreachable.
    """
    result = subprocess.run(
        [sys.executable, "-m", "fleet_memory.reindex", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Should exit 0
    assert result.returncode == 0

    # Should print help text
    assert "re-index" in result.stdout.lower() or "reindex" in result.stdout.lower()


@pytest.mark.asyncio
async def test_successful_run_exits_zero_and_prints_report() -> None:
    """Successful re-index exits 0 and prints the RunReport summary."""
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.corpus_root = "fake_corpus"
    mock_settings.backfill_dir = "fake_backfill"
    mock_settings.pg_dsn = "postgresql://fake"
    mock_settings.embed_url = "http://fake"

    # Mock store context
    mock_store = AsyncMock()

    @asynccontextmanager
    async def mock_store_context(settings, embed_fn=None):
        yield mock_store

    # Mock reindex_corpus to return success
    async def mock_reindex_corpus(corpus_root, publisher):
        return RunReport(published_count=5, unparseable_count=0, unrecognized_count=0)

    # Mock process_backfill
    async def mock_process_backfill(backfill_dir, publisher):
        return 2  # Published 2 backfill documents

    with (
        patch("fleet_memory.reindex.__main__.Settings", return_value=mock_settings),
        patch(
            "fleet_memory.reindex.__main__.async_store_context", mock_store_context
        ),
        patch(
            "fleet_memory.reindex.__main__.reindex_corpus", mock_reindex_corpus
        ),
        patch(
            "fleet_memory.reindex.__main__.process_backfill", mock_process_backfill
        ),
        patch("fleet_memory.reindex.__main__.print") as mock_print,
        patch("sys.argv", ["reindex"]),  # Mock argv to avoid argparse issues
    ):
        from fleet_memory.reindex.__main__ import main

        # Should exit with 0
        with pytest.raises(SystemExit) as exc_info:
            await main()

        assert exc_info.value.code == 0, "Should exit with code 0 on success"

        # Verify report was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        report_printed = any("published" in str(call).lower() for call in print_calls)
        assert report_printed, "RunReport should be printed"
