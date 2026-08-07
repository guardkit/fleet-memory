"""The bounded acknowledgement: a dated deferral that cannot become a mute button.

The rule the whole design turns on: **never silently honoured, never silently ignored.**
Every rejection has to say why, in words, in the run's own output — otherwise the ack
file becomes the new place darkness hides.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from fleet_memory.fence.ack import read_ack

TODAY = date(2026, 8, 7)


@pytest.fixture
def ack_path(tmp_path: Path) -> Path:
    return tmp_path / "liveness-fence.ack"


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_no_file_means_no_acknowledgement_and_no_complaint(ack_path: Path):
    ack = read_ack(ack_path, today=TODAY)
    assert ack.present is False
    assert ack.active is False
    assert ack.note() is None
    assert ack.holds("relay_idle") is False


def test_a_valid_ack_holds_the_check_it_names(ack_path: Path):
    _write(
        ack_path,
        {
            "reason": "waiting on the capture-outcome wiring",
            "until": (TODAY + timedelta(days=11)).isoformat(),
            "checks": ["relay_idle"],
        },
    )
    ack = read_ack(ack_path, today=TODAY)
    assert ack.active is True
    assert ack.holds("relay_idle") is True
    assert ack.holds("store_age") is False
    assert ack.note() is None


def test_an_ack_expiring_today_still_holds(ack_path: Path):
    _write(
        ack_path,
        {"reason": "last day", "until": TODAY.isoformat(), "checks": ["store_age"]},
    )
    ack = read_ack(ack_path, today=TODAY)
    assert ack.holds("store_age") is True


def test_an_expired_ack_stops_holding_and_says_when_it_lapsed(ack_path: Path):
    lapsed = TODAY - timedelta(days=1)
    _write(ack_path, {"reason": "stale", "until": lapsed.isoformat(), "checks": ["relay_idle"]})
    ack = read_ack(ack_path, today=TODAY)
    assert ack.active is False
    assert ack.holds("relay_idle") is False
    assert ack.note() == f"ack expired on {lapsed.isoformat()}"


def test_an_ack_more_than_fourteen_days_out_is_rejected_and_says_why(ack_path: Path):
    _write(
        ack_path,
        {
            "reason": "indefinitely",
            "until": (TODAY + timedelta(days=15)).isoformat(),
            "checks": ["relay_idle"],
        },
    )
    ack = read_ack(ack_path, today=TODAY)
    assert ack.active is False
    assert ack.holds("relay_idle") is False
    assert "more than 14 days away" in ack.rejected
    assert ack.note().startswith("ack rejected:")


def test_exactly_fourteen_days_out_is_accepted(ack_path: Path):
    _write(
        ack_path,
        {
            "reason": "the full bounded window",
            "until": (TODAY + timedelta(days=14)).isoformat(),
            "checks": ["relay_idle"],
        },
    )
    assert read_ack(ack_path, today=TODAY).holds("relay_idle") is True


def test_a_missing_until_is_rejected(ack_path: Path):
    _write(ack_path, {"reason": "forever please", "checks": ["relay_idle"]})
    ack = read_ack(ack_path, today=TODAY)
    assert "silent waiver" in ack.rejected
    assert ack.holds("relay_idle") is False


def test_an_unparseable_until_is_rejected(ack_path: Path):
    _write(ack_path, {"reason": "soon", "until": "next Tuesday", "checks": ["relay_idle"]})
    ack = read_ack(ack_path, today=TODAY)
    assert "not a YYYY-MM-DD date" in ack.rejected


def test_an_ack_naming_no_checks_is_rejected(ack_path: Path):
    _write(ack_path, {"reason": "everything", "until": TODAY.isoformat(), "checks": []})
    ack = read_ack(ack_path, today=TODAY)
    assert "must name what it covers" in ack.rejected


def test_an_ack_with_no_reason_is_rejected(ack_path: Path):
    _write(ack_path, {"until": TODAY.isoformat(), "checks": ["relay_idle"]})
    ack = read_ack(ack_path, today=TODAY)
    assert "must say why" in ack.rejected


def test_malformed_json_is_rejected_not_a_crash(ack_path: Path):
    ack_path.write_text("{oops", encoding="utf-8")
    ack = read_ack(ack_path, today=TODAY)
    assert ack.present is True
    assert "not readable JSON" in ack.rejected


def test_a_json_list_is_rejected(ack_path: Path):
    _write(ack_path, ["relay_idle"])
    assert "not a JSON object" in read_ack(ack_path, today=TODAY).rejected


def test_an_unreadable_file_is_rejected_not_a_crash(tmp_path: Path):
    locked = tmp_path / "locked"
    locked.mkdir()
    target = locked / "liveness-fence.ack"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o000)
    try:
        ack = read_ack(target, today=TODAY)
    finally:
        os.chmod(target, 0o600)
    if ack.rejected:
        assert "could not be read" in ack.rejected
    else:  # running as root — the file was readable after all
        assert ack.present is True


def test_the_status_dict_records_the_hard_ceiling(ack_path: Path):
    """The 14-day maximum is a constant, not a setting — the record says so."""
    _write(
        ack_path,
        {"reason": "x", "until": (TODAY + timedelta(days=3)).isoformat(), "checks": ["store_age"]},
    )
    assert read_ack(ack_path, today=TODAY).as_dict()["max_days"] == 14
