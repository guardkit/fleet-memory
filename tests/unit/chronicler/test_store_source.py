"""Unit tests for the Chronicler's store-reading seam (since-bound semantics).

The scheduled-run finding this pins: 588/1090 live rows carry no occurred_at.
An always-include fallback re-emits every one of them on each daily timer run —
the since-bound must fall back to the store item's created_at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fleet_memory.chronicler.store_source import read_episodes


@dataclass
class StubItem:
    """Store search item stub: value + created_at (AsyncPostgresStore surface)."""

    value: dict[str, Any]
    created_at: Any = None


@dataclass
class StubStore:
    """Store stub serving one namespace of items."""

    items: list[StubItem] = field(default_factory=list)

    async def alist_namespaces(self, *, prefix, max_depth, limit):
        return [("fleet_memory", "guardkit", "build_outcome")]

    async def asearch(self, namespace, *, limit):
        return self.items


def _value(natural_key: str, occurred_at: str | None = None) -> dict[str, Any]:
    value = {
        "payload_type": "build_outcome",
        "natural_key": natural_key,
        "identifier": natural_key.rsplit(":", 1)[-1],
        "project": "guardkit",
        "content": json.dumps({"status": "success"}),
    }
    if occurred_at is not None:
        value["episode_meta"] = {"occurred_at": occurred_at}
    return value


class TestSinceBoundFallback:
    """Undated episodes use the store item's created_at for the since-bound."""

    async def test_undated_before_since_is_excluded_via_created_at(self) -> None:
        """The 588-undated-rows fix: an old undated row stops re-emitting."""
        store = StubStore(
            items=[
                StubItem(
                    value=_value("build_outcome:guardkit:OLD"),
                    created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
                )
            ]
        )

        episodes = await read_episodes(store, since="2026-07-01T00:00:00+00:00")

        assert episodes == []

    async def test_undated_after_since_is_included_via_created_at(self) -> None:
        store = StubStore(
            items=[
                StubItem(
                    value=_value("build_outcome:guardkit:NEW"),
                    created_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
                )
            ]
        )

        episodes = await read_episodes(store, since="2026-07-01T00:00:00+00:00")

        assert len(episodes) == 1
        assert episodes[0].natural_key == "build_outcome:guardkit:NEW"

    async def test_occurred_at_wins_over_created_at(self) -> None:
        """A dated episode is bounded on occurred_at even when created_at differs."""
        store = StubStore(
            items=[
                StubItem(
                    value=_value(
                        "build_outcome:guardkit:DATED",
                        occurred_at="2026-06-01T00:00:00+00:00",
                    ),
                    # Row re-written recently, but the EVENT is old
                    created_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
                )
            ]
        )

        episodes = await read_episodes(store, since="2026-07-01T00:00:00+00:00")

        assert episodes == []

    async def test_undated_and_no_created_at_still_included(self) -> None:
        """Neither timestamp -> still included (never silently dropped)."""
        store = StubStore(
            items=[StubItem(value=_value("build_outcome:guardkit:NOSTAMP"))]
        )

        episodes = await read_episodes(store, since="2026-07-01T00:00:00+00:00")

        assert len(episodes) == 1

    async def test_string_created_at_supported(self) -> None:
        store = StubStore(
            items=[
                StubItem(
                    value=_value("build_outcome:guardkit:STR"),
                    created_at="2026-06-01T00:00:00+00:00",
                )
            ]
        )

        episodes = await read_episodes(store, since="2026-07-01T00:00:00+00:00")

        assert episodes == []

    async def test_no_since_includes_everything(self) -> None:
        store = StubStore(
            items=[
                StubItem(value=_value("build_outcome:guardkit:A")),
                StubItem(
                    value=_value("build_outcome:guardkit:B"),
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ]
        )

        episodes = await read_episodes(store)

        assert len(episodes) == 2
