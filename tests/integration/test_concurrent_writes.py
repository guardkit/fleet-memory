"""Integration tests for concurrent write semantics and MVCC isolation.

Marker-gated (@pytest.mark.integration) tests validating that concurrent writes to the same key
converge on one complete winner (ASSUM-003) and that reads during concurrent writes never observe
partial data (ASSUM-013). Relies on PostgreSQL MVCC for atomic visibility.

Requirements:
- Docker running for ephemeral_pg fixture
- Run with: pytest -m integration tests/integration/test_concurrent_writes.py
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.integration
async def test_concurrent_same_key_writes_converge_on_one_winner(store_context) -> None:
    """Concurrent same-key writes: exactly one complete winner, never a blend.

    AC-002 (ASSUM-003): Two aput calls to the same key with different content lengths
    via asyncio.gather. After both complete, aget returns exactly one of the two versions
    in full - never a blend, never partial content.

    Uses distinct content lengths so a blend would be detectable by length alone.
    """
    store, namespace = store_context

    test_key = "concurrent_write_target"

    # Version 1: short content (20 chars)
    version_1_content = {
        "content": "Short version A here",  # 20 chars
        "version": 1,
        "marker": "VERSION_ONE",
    }

    # Version 2: long content (100+ chars)
    version_2_content = {
        "content": (
            "This is a much longer version B with significantly more text content "
            "to ensure that any partial write or blend would be detectable by the "
            "content length alone and make the test failure obvious."
        ),  # 200+ chars
        "version": 2,
        "marker": "VERSION_TWO",
    }

    # Launch concurrent writes - both target the same key
    write_results = await asyncio.gather(
        store.aput(namespace, test_key, version_1_content),
        store.aput(namespace, test_key, version_2_content),
        return_exceptions=True,
    )

    # Verify both writes completed without exceptions
    for idx, result in enumerate(write_results):
        assert not isinstance(result, Exception), (
            f"Write {idx} failed with exception: {result}"
        )

    # Retrieve the final value
    final_record = await store.aget(namespace, test_key)

    # Verify exactly one complete winner exists
    assert final_record is not None, "aget must return a record after concurrent writes"
    final_value = final_record.value

    # Verify it's one of the two versions in full - never a blend
    is_version_1 = (
        final_value.get("version") == 1
        and final_value.get("marker") == "VERSION_ONE"
        and final_value.get("content") == version_1_content["content"]
    )
    is_version_2 = (
        final_value.get("version") == 2
        and final_value.get("marker") == "VERSION_TWO"
        and final_value.get("content") == version_2_content["content"]
    )

    assert is_version_1 or is_version_2, (
        f"Final value must be exactly version 1 or version 2, not a blend. "
        f"Got: version={final_value.get('version')}, "
        f"marker={final_value.get('marker')}, "
        f"content_length={len(final_value.get('content', ''))}"
    )

    # Additional check: content length must match one of the originals exactly
    final_content_len = len(final_value.get("content", ""))
    version_1_len = len(version_1_content["content"])
    version_2_len = len(version_2_content["content"])

    assert final_content_len == version_1_len or final_content_len == version_2_len, (
        f"Content length {final_content_len} doesn't match either original "
        f"({version_1_len} or {version_2_len}), suggesting a blend or corruption"
    )


@pytest.mark.integration
async def test_read_during_write_observes_complete_version_only(store_context) -> None:
    """Read-during-write: reader sees complete old or complete new, never partial.

    AC-003 (ASSUM-013): A reader polling asearch/aget while a writer rewrites the same key
    only ever observes the complete old version or the complete new version. Never a partial
    write, never a blend of old and new fields.

    Uses a bounded iteration count (50 iterations) for determinism in CI.
    """
    store, namespace = store_context

    test_key = "read_write_race_target"

    # Initial version: distinctive marker and content
    old_version = {
        "content": "Original content before concurrent rewrite",
        "state": "OLD",
        "marker": "BEFORE_REWRITE",
        "sequence": 0,
    }

    await store.aput(namespace, test_key, old_version)

    # New version: completely different marker and content
    new_version = {
        "content": "Updated content after concurrent rewrite operation completed successfully",
        "state": "NEW",
        "marker": "AFTER_REWRITE",
        "sequence": 1,
    }

    # Track what versions readers observe
    observed_versions: list[dict] = []
    read_complete = asyncio.Event()

    async def concurrent_reader() -> None:
        """Poll aget repeatedly and record observed versions."""
        for _ in range(50):  # Bounded iteration for CI determinism
            record = await store.aget(namespace, test_key)
            if record:
                observed_versions.append(record.value.copy())
            await asyncio.sleep(0.001)  # Small delay to allow writer to proceed
        read_complete.set()

    async def concurrent_writer() -> None:
        """Rewrite the key with new version."""
        await asyncio.sleep(0.01)  # Let reader start first
        await store.aput(namespace, test_key, new_version)

    # Run reader and writer concurrently
    await asyncio.gather(
        concurrent_reader(),
        concurrent_writer(),
    )

    # Wait for reader to finish
    await read_complete.wait()

    # Verify we observed at least some versions during the race
    assert len(observed_versions) > 0, "Reader should have observed at least one version"

    # Verify every observed version is either complete OLD or complete NEW
    for idx, observed in enumerate(observed_versions):
        is_old_complete = (
            observed.get("state") == "OLD"
            and observed.get("marker") == "BEFORE_REWRITE"
            and observed.get("sequence") == 0
            and observed.get("content") == old_version["content"]
        )
        is_new_complete = (
            observed.get("state") == "NEW"
            and observed.get("marker") == "AFTER_REWRITE"
            and observed.get("sequence") == 1
            and observed.get("content") == new_version["content"]
        )

        assert is_old_complete or is_new_complete, (
            f"Observation {idx} is neither complete OLD nor complete NEW. "
            f"Got: state={observed.get('state')}, "
            f"marker={observed.get('marker')}, "
            f"sequence={observed.get('sequence')}. "
            f"This indicates a partial write was visible, violating MVCC isolation."
        )

    # Statistical check: we should observe at least one transition from old to new
    # (though it's theoretically possible all reads hit before or after the write)
    states_seen = {obs.get("state") for obs in observed_versions}
    # This is informational - the critical check is that no partial versions were seen
    # But in practice with 50 iterations, we expect to see both states
    # (commented out to avoid flakiness in fast writes)
    # assert "OLD" in states_seen or "NEW" in states_seen


@pytest.mark.integration
async def test_asearch_during_concurrent_writes_returns_complete_items(store_context) -> None:
    """Search during concurrent writes: all returned items are complete versions.

    Supplements AC-003: verify asearch (not just aget) observes atomic visibility.
    Reader polls asearch while writers update multiple keys concurrently.
    Every returned item must have complete, consistent metadata.
    """
    store, namespace = store_context

    # Initial state: two items with "BEFORE" markers
    initial_items = {
        "item_1": {"content": "First item initial state", "state": "BEFORE", "id": 1},
        "item_2": {"content": "Second item initial state", "state": "BEFORE", "id": 2},
    }

    for key, value in initial_items.items():
        await store.aput(namespace, key, value)

    # Updated versions: "AFTER" markers with different content
    updated_items = {
        "item_1": {"content": "First item updated state", "state": "AFTER", "id": 1},
        "item_2": {"content": "Second item updated state", "state": "AFTER", "id": 2},
    }

    observed_searches: list[list] = []
    search_complete = asyncio.Event()

    async def concurrent_searcher() -> None:
        """Poll asearch and record all results."""
        for _ in range(30):  # Bounded iteration
            results = await store.asearch(namespace, limit=10)
            # Record copy of search results
            observed_searches.append([r.value.copy() for r in results])
            await asyncio.sleep(0.001)
        search_complete.set()

    async def concurrent_updater() -> None:
        """Update both items concurrently."""
        await asyncio.sleep(0.005)  # Let searcher start
        await asyncio.gather(
            store.aput(namespace, "item_1", updated_items["item_1"]),
            store.aput(namespace, "item_2", updated_items["item_2"]),
        )

    # Run searcher and updater concurrently
    await asyncio.gather(
        concurrent_searcher(),
        concurrent_updater(),
    )

    await search_complete.wait()

    # Verify we got search results
    assert len(observed_searches) > 0, "Should have observed search results"

    # Verify every item in every search result is a complete version
    for search_idx, search_results in enumerate(observed_searches):
        for item_idx, item in enumerate(search_results):
            item_id = item.get("id")

            # Must have consistent state marker and content
            is_before_complete = (
                item.get("state") == "BEFORE"
                and "initial state" in item.get("content", "")
            )
            is_after_complete = (
                item.get("state") == "AFTER"
                and "updated state" in item.get("content", "")
            )

            assert is_before_complete or is_after_complete, (
                f"Search {search_idx}, item {item_idx} (id={item_id}) has inconsistent state. "
                f"Got: state={item.get('state')}, content={item.get('content')[:50]}. "
                f"This suggests a partial write was visible in search results."
            )
