"""The relay's progress marker: written atomically, read tolerantly, never fatal.

Two properties matter more than any field:

1. **Writing it can never cost a message.** Every failure mode must return quietly.
2. **Reading it can never crash the fence.** Absent, truncated, corrupt, wrong shape —
   all become BLIND, which the checker turns into a loud alarm.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fleet_memory.fence.marker import MARKER_SCHEMA, RelayMarker, read_marker


@pytest.fixture
def marker_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "relay-progress.json"


def test_write_read_round_trip(marker_path: Path):
    marker = RelayMarker(marker_path)
    marker.record_start()
    marker.record_ingest()

    read = read_marker(marker_path)
    assert not read.blind
    assert read.state.started_at is not None
    assert read.state.last_ingest_at is not None
    assert read.state.ingests_since_start == 1
    assert read.state.messages_since_start == 1
    assert read.state.last_disposition == "ack"


def test_the_file_is_one_line_of_json_with_the_documented_shape(marker_path: Path):
    marker = RelayMarker(marker_path)
    marker.record_start()
    marker.record_ingest()
    data = json.loads(marker_path.read_text(encoding="utf-8"))
    assert data["schema"] == MARKER_SCHEMA
    assert set(data) == {
        "schema",
        "started_at",
        "last_message_at",
        "last_ingest_at",
        "messages_since_start",
        "ingests_since_start",
        "last_disposition",
    }


def test_counters_increment(marker_path: Path):
    marker = RelayMarker(marker_path)
    marker.record_start()
    for _ in range(3):
        marker.record_ingest()
    marker.record_message(disposition="dlq")

    state = read_marker(marker_path).state
    assert state.ingests_since_start == 3
    assert state.messages_since_start == 4
    assert state.last_disposition == "dlq"


def test_a_failed_message_moves_last_message_but_not_last_ingest(marker_path: Path):
    """This is what lets an operator see 'receiving but failing' at a glance."""
    marker = RelayMarker(marker_path)
    marker.record_start()
    marker.record_ingest()
    ingest_at = read_marker(marker_path).state.last_ingest_at
    marker.record_message(disposition="nak")

    state = read_marker(marker_path).state
    assert state.last_ingest_at == ingest_at
    assert state.last_message_at >= ingest_at
    assert state.last_disposition == "nak"


def test_record_start_preserves_the_previous_process_history(marker_path: Path):
    """A container recreate must not erase the evidence the fence judges on."""
    first = RelayMarker(marker_path)
    first.record_start()
    first.record_ingest()
    original_ingest = read_marker(marker_path).state.last_ingest_at

    second = RelayMarker(marker_path)
    second.record_start()

    state = read_marker(marker_path).state
    assert state.last_ingest_at == original_ingest  # carried over
    assert state.ingests_since_start == 0  # but the counters are for THIS process
    assert state.started_at >= original_ingest


def test_the_write_is_atomic_leaving_no_stray_temp_files(marker_path: Path):
    marker = RelayMarker(marker_path)
    marker.record_start()
    marker.record_ingest()
    leftovers = [p.name for p in marker_path.parent.iterdir() if p.name != marker_path.name]
    assert leftovers == []


def test_missing_file_is_blind_with_a_plain_language_reason(tmp_path: Path):
    read = read_marker(tmp_path / "nope.json")
    assert read.blind
    assert "has not written one yet" in read.problem


def test_corrupt_json_is_blind_not_a_crash(marker_path: Path):
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("{not json at all", encoding="utf-8")
    read = read_marker(marker_path)
    assert read.blind
    assert "not readable JSON" in read.problem


def test_truncated_file_is_blind_not_a_crash(marker_path: Path):
    marker = RelayMarker(marker_path)
    marker.record_start()
    full = marker_path.read_text(encoding="utf-8")
    marker_path.write_text(full[: len(full) // 2], encoding="utf-8")
    assert read_marker(marker_path).blind


def test_an_empty_file_is_blind(marker_path: Path):
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("", encoding="utf-8")
    assert read_marker(marker_path).blind


def test_json_that_is_not_an_object_is_blind(marker_path: Path):
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("[1, 2, 3]", encoding="utf-8")
    read = read_marker(marker_path)
    assert read.blind
    assert "expected shape" in read.problem


def test_a_marker_without_a_start_time_is_blind(marker_path: Path):
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(json.dumps({"schema": 1, "last_ingest_at": None}), encoding="utf-8")
    read = read_marker(marker_path)
    assert read.blind
    assert "no start time" in read.problem


def test_an_unwritable_path_returns_silently_and_never_raises(tmp_path: Path):
    """An ack must never depend on a filesystem write."""
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o500)  # readable, not writable
    try:
        marker = RelayMarker(locked / "sub" / "relay-progress.json")
        marker.record_start()  # must not raise
        marker.record_ingest()  # must not raise
        marker.record_message(disposition="dlq")  # must not raise
    finally:
        os.chmod(locked, 0o755)


def test_only_one_warning_is_logged_per_process(tmp_path: Path, caplog):
    """A per-message log line on a broken disk would drown the journal."""
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o500)
    try:
        marker = RelayMarker(locked / "sub" / "relay-progress.json")
        with caplog.at_level("WARNING", logger="fleet_memory.fence.marker"):
            for _ in range(5):
                marker.record_ingest()
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
    finally:
        os.chmod(locked, 0o755)


def test_timestamps_are_read_back_as_aware_utc(marker_path: Path):
    marker = RelayMarker(marker_path)
    marker.record_start()
    marker.record_ingest()
    state = read_marker(marker_path).state
    assert state.started_at.tzinfo is not None
    assert state.last_ingest_at <= datetime.now(UTC)


def test_a_home_relative_path_is_expanded(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    marker = RelayMarker("~/.local/state/fleet-memory/relay-progress.json")
    marker.record_start()
    assert (tmp_path / ".local/state/fleet-memory/relay-progress.json").exists()
