"""Integration tests for hostile content safety (SQL injection resistance).

Marker-gated (@pytest.mark.integration) tests validating:
- SQL injection-shaped text round-trips byte-identical
- Hostile content appears normally in search results
- No corruption of other memories or store structure

Requirements:
- Docker running for ephemeral_pg fixture
- Default test run (pytest) skips these; run with: pytest -m integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
async def test_sql_injection_text_round_trips_byte_identical(store_context) -> None:
    """Hostile content: SQL injection text round-trips byte-identical via aput/aget.

    AC-005 (part 1): Store a memory containing SQL injection-shaped text
    (e.g., "'; DROP TABLE memories; --") and verify it round-trips byte-identical.
    """
    store, namespace = store_context

    # SQL injection payloads to test
    hostile_payloads = [
        "'; DROP TABLE memories; --",
        "1' OR '1'='1",
        "admin'--",
        "' UNION SELECT * FROM users; --",
        "Robert'); DROP TABLE students;--",  # Classic "Bobby Tables"
    ]

    for i, payload in enumerate(hostile_payloads):
        key = f"hostile_content_{i}"
        content = {
            "content": payload,
            "metadata": {"test": "sql_injection", "index": i},
        }

        # Store the hostile content
        await store.aput(namespace, key, content)

        # Retrieve and verify byte-identical round-trip
        retrieved = await store.aget(namespace, key)

        assert retrieved is not None, f"Hostile content should be retrievable for payload: {payload}"
        assert retrieved.value == content, (
            f"Retrieved content must be byte-identical to stored content. "
            f"Payload: {payload}"
        )
        assert retrieved.value["content"] == payload, (
            f"Content field must match exactly. Expected: {payload!r}, "
            f"Got: {retrieved.value['content']!r}"
        )


@pytest.mark.integration
async def test_hostile_content_appears_in_search_results(store_context) -> None:
    """Hostile content: SQL injection text appears normally in search results.

    AC-005 (part 2): Verify that hostile content is searchable and appears
    in search results without causing errors or corruption.
    """
    store, namespace = store_context

    # Store a mix of hostile and normal content
    hostile_key = "sql_injection_memory"
    hostile_content = {
        "content": "'; DROP TABLE memories; -- This is hostile SQL injection text",
        "metadata": {"type": "hostile"},
    }

    normal_key = "normal_memory"
    normal_content = {
        "content": "This is normal database documentation about DROP TABLE operations",
        "metadata": {"type": "normal"},
    }

    await store.aput(namespace, hostile_key, hostile_content)
    await store.aput(namespace, normal_key, normal_content)

    # Search for content that should match both
    results = await store.asearch(namespace, query="DROP TABLE")

    # Verify we got results
    assert len(results) > 0, "Search should return results for 'DROP TABLE'"

    # Verify hostile content appears in results
    result_keys = {item.key for item in results}
    assert hostile_key in result_keys, "Hostile content should appear in search results"

    # Verify the hostile content in search results is intact
    hostile_result = next(item for item in results if item.key == hostile_key)
    assert hostile_result.value["content"].startswith("'; DROP TABLE memories; --"), (
        "Hostile content in search results should be intact"
    )


@pytest.mark.integration
async def test_hostile_content_does_not_affect_other_memories(store_context) -> None:
    """Hostile content: storing hostile text does not corrupt other memories.

    AC-005 (part 3): Verify that storing SQL injection text does not affect
    other memories or store structure.
    """
    store, namespace = store_context

    # Store normal memories first
    normal_keys = []
    for i in range(5):
        key = f"normal_memory_{i}"
        content = {
            "content": f"Normal memory {i} about database best practices",
            "index": i,
        }
        await store.aput(namespace, key, content)
        normal_keys.append(key)

    # Verify all normal memories are stored
    for key in normal_keys:
        retrieved = await store.aget(namespace, key)
        assert retrieved is not None, f"Normal memory {key} should exist"

    # Store hostile content
    hostile_key = "hostile_injection"
    hostile_content = {
        "content": "'; DELETE FROM memories WHERE 1=1; --",
        "metadata": {"danger": "high"},
    }
    await store.aput(namespace, hostile_key, hostile_content)

    # Verify all normal memories are still intact
    for i, key in enumerate(normal_keys):
        retrieved = await store.aget(namespace, key)
        assert retrieved is not None, (
            f"Normal memory {key} should still exist after hostile content storage"
        )
        assert retrieved.value["content"] == f"Normal memory {i} about database best practices", (
            f"Normal memory {key} content should be unchanged"
        )

    # Verify hostile content is also stored correctly
    hostile_retrieved = await store.aget(namespace, hostile_key)
    assert hostile_retrieved is not None, "Hostile content should be stored"
    assert hostile_retrieved.value == hostile_content, "Hostile content should be intact"

    # Verify search returns all memories
    all_results = await store.asearch(namespace)
    assert len(all_results) >= 6, (
        f"Should have at least 6 memories (5 normal + 1 hostile), got {len(all_results)}"
    )


@pytest.mark.integration
async def test_unicode_and_special_characters_round_trip(store_context) -> None:
    """Hostile content: Unicode and special characters round-trip safely.

    Extended test for AC-005: Verify that various special characters and
    Unicode text are handled safely.
    """
    store, namespace = store_context

    special_content_examples = [
        {"content": "Emoji test: 🚀 🔥 💾 🗄️", "type": "emoji"},
        {"content": "Unicode: résumé café naïve", "type": "unicode"},
        {"content": "Quotes: \"double\" 'single' `backtick`", "type": "quotes"},
        {"content": "Backslashes: \\n \\t \\\\ \\x00", "type": "backslash"},
        {"content": "Percent encoding: %20 %2F %3A", "type": "percent"},
    ]

    for i, content in enumerate(special_content_examples):
        key = f"special_char_{i}"

        # Store the content
        await store.aput(namespace, key, content)

        # Retrieve and verify byte-identical
        retrieved = await store.aget(namespace, key)
        assert retrieved is not None, f"Special content should be retrievable: {content['type']}"
        assert retrieved.value == content, (
            f"Special content should round-trip byte-identical for type: {content['type']}"
        )
