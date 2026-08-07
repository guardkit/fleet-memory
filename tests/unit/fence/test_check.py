"""The fence's decision table — the heart of the rung.

``evaluate`` is pure: facts in, verdict out, with ``now`` injected. So every row of
the table below is a plain function call with no database, no filesystem, and no
clock. If this file is green, the fence's judgement is right; everything else is
plumbing that feeds it.

The property under test throughout: **the fence never reports OK when it cannot see.**
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from fleet_memory.fence import Status
from fleet_memory.fence.ack import AckState
from fleet_memory.fence.builds import BuildReceipt, BuildScan
from fleet_memory.fence.check import FenceFacts, Thresholds, evaluate, humanise_age
from fleet_memory.fence.marker import MarkerRead, MarkerState
from fleet_memory.fence.store_age import ProjectFacts, StoreFacts

NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
THRESHOLDS = Thresholds(
    store_max_age_hours=168,
    build_window_hours=72,
    min_builds_in_window=3,
    relay_restart_grace_minutes=75,
    watch_projects=("guardkit",),
)


def _store(
    *,
    age_hours: float = 4.0,
    rows: int = 3661,
    reachable: bool = True,
    problem: str | None = None,
    projects: tuple[ProjectFacts, ...] = (),
) -> StoreFacts:
    if not reachable:
        return StoreFacts(target="db.example:5433/fleet_memory", reachable=False, problem=problem)
    newest = NOW - timedelta(hours=age_hours)
    return StoreFacts(
        target="db.example:5433/fleet_memory",
        reachable=True,
        newest_updated_at=newest,
        newest_created_at=newest,
        row_count=rows,
        per_project=projects,
    )


def _project(name: str, *, age_hours: float, rows: int = 10) -> ProjectFacts:
    newest = NOW - timedelta(hours=age_hours)
    return ProjectFacts(
        project=name, newest_updated_at=newest, newest_created_at=newest, row_count=rows
    )


def _builds(count: int, *, spread_hours: float = 48.0) -> BuildScan:
    receipts = tuple(
        BuildReceipt(
            name=f"build-FEAT-TST{i}-2026080{i}000000",
            feature=f"FEAT-TST{i}",
            finished_at=NOW - timedelta(hours=spread_hours * (i + 1) / max(count, 1)),
        )
        for i in range(count)
    )
    return BuildScan(receipts=receipts, path="/receipts")


def _marker(
    *,
    started_hours_ago: float = 300.0,
    last_ingest_hours_ago: float | None = 2.0,
    last_message_hours_ago: float | None = None,
    ingests: int = 6,
) -> MarkerRead:
    state = MarkerState(
        started_at=NOW - timedelta(hours=started_hours_ago),
        last_ingest_at=(
            None if last_ingest_hours_ago is None else NOW - timedelta(hours=last_ingest_hours_ago)
        ),
        last_message_at=(
            None
            if last_message_hours_ago is None
            else NOW - timedelta(hours=last_message_hours_ago)
        ),
        messages_since_start=ingests,
        ingests_since_start=ingests,
        last_disposition="ack",
    )
    return MarkerRead(state=state, problem=None, path="/state/relay-progress.json")


def _by_name(report, name):
    return next(c for c in report.checks if c.name == name)


# --- store max-age ---------------------------------------------------------------


def test_fresh_store_is_ok():
    report = evaluate(FenceFacts(store=_store(age_hours=4)), THRESHOLDS, NOW, store_only=True)
    assert report.status is Status.OK
    assert _by_name(report, "store_age").status is Status.OK
    assert "4 hours old" in _by_name(report, "store_age").message


def test_store_one_hour_past_the_limit_alarms():
    report = evaluate(FenceFacts(store=_store(age_hours=169)), THRESHOLDS, NOW, store_only=True)
    check = _by_name(report, "store_age")
    assert report.status is Status.ALARM
    assert check.reason == "STORE_STALE"
    assert "7 days" in check.message  # the limit is stated in the words an operator reads


def test_store_exactly_at_the_limit_is_still_ok():
    """The boundary is not the alarm — only past it is."""
    report = evaluate(FenceFacts(store=_store(age_hours=168)), THRESHOLDS, NOW, store_only=True)
    assert report.status is Status.OK


def test_watched_project_stale_while_whole_store_is_fresh_alarms():
    """The whole store looking healthy must not hide one dark project."""
    facts = _store(age_hours=2, projects=(_project("guardkit", age_hours=400),))
    report = evaluate(FenceFacts(store=facts), THRESHOLDS, NOW, store_only=True)
    assert _by_name(report, "store_age").status is Status.OK
    assert _by_name(report, "store_age:guardkit").status is Status.ALARM
    assert report.status is Status.ALARM
    assert "guardkit" in _by_name(report, "store_age:guardkit").message


def test_watched_project_with_no_rows_at_all_alarms():
    facts = _store(age_hours=2, projects=(_project("guardkit", age_hours=1, rows=0),))
    report = evaluate(FenceFacts(store=facts), THRESHOLDS, NOW, store_only=True)
    check = _by_name(report, "store_age:guardkit")
    assert check.status is Status.ALARM
    assert check.reason == "STORE_EMPTY"


def test_unreachable_store_alarms_rather_than_crashing():
    """The Chronicler failed three scheduled runs on a connection timeout and nothing
    surfaced it. Surfacing that is the fence's job, so it must survive to report it."""
    facts = _store(reachable=False, problem="cannot reach the memory store at db.example:5433/x")
    report = evaluate(FenceFacts(store=facts), THRESHOLDS, NOW, store_only=True)
    check = _by_name(report, "store_age")
    assert report.status is Status.ALARM
    assert check.reason == "STORE_UNREACHABLE"


def test_empty_store_alarms():
    report = evaluate(
        FenceFacts(store=_store(rows=0)), THRESHOLDS, NOW, store_only=True
    )
    assert _by_name(report, "store_age").reason == "STORE_EMPTY"
    assert report.status is Status.ALARM


def test_store_facts_absent_is_blind_not_ok():
    report = evaluate(FenceFacts(store=None), THRESHOLDS, NOW, store_only=True)
    assert _by_name(report, "store_age").reason == "BLIND"
    assert report.status is Status.ALARM


# --- relay idle ------------------------------------------------------------------


def test_builds_ran_and_relay_wrote_nothing_alarms():
    facts = FenceFacts(
        builds=_builds(4),
        marker=_marker(last_ingest_hours_ago=200.0, started_hours_ago=300.0),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    check = _by_name(report, "relay_idle")
    assert report.status is Status.ALARM
    assert check.reason == "RELAY_IDLE"
    # The sentence names BOTH possible causes, because both are real today.
    assert "relay is not consuming" in check.message
    assert "close ritual" in check.message


def test_builds_ran_and_relay_wrote_recently_is_ok():
    facts = FenceFacts(builds=_builds(4), marker=_marker(last_ingest_hours_ago=2.0))
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").status is Status.OK
    assert report.status is Status.OK


def test_too_few_builds_to_judge_is_ok():
    facts = FenceFacts(builds=_builds(2), marker=_marker(last_ingest_hours_ago=500.0))
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").status is Status.OK


def test_too_few_builds_names_the_threshold_as_well_as_the_count():
    """The line has to read straight when the threshold, not the count, is unusual.

    Raise --min-builds above what the box actually does and the old wording said
    "only 3 builds finished", which sounds like the box went quiet when in fact the
    operator moved the bar. Both numbers appear so it is obvious which one moved.
    """
    thresholds = replace(THRESHOLDS, min_builds_in_window=9)
    facts = FenceFacts(builds=_builds(3), marker=_marker(last_ingest_hours_ago=500.0))
    report = evaluate(facts, thresholds, NOW, relay_only=True)

    check = _by_name(report, "relay_idle")
    assert check.status is Status.OK
    assert "3 builds finished" in check.message
    assert "9" in check.message
    assert "only 3" not in check.message
    assert check.detail["min_builds_in_window"] == 9


def test_zero_builds_is_ok_because_quiet_days_are_legitimately_quiet():
    facts = FenceFacts(
        builds=BuildScan(receipts=(), path="/receipts"),
        marker=_marker(last_ingest_hours_ago=None, ingests=0),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").status is Status.OK
    assert report.status is Status.OK


def test_relay_restarted_ten_minutes_ago_is_held_by_the_grace_period():
    """A container recreate orphans an in-flight delivery until ack_wait expires."""
    facts = FenceFacts(
        builds=_builds(4),
        marker=_marker(started_hours_ago=10 / 60, last_ingest_hours_ago=None, ingests=0),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    check = _by_name(report, "relay_idle")
    assert check.status is Status.OK
    assert check.reason == "RELAY_RESTART_GRACE"


def test_relay_restarted_three_hours_ago_is_past_the_grace_period():
    facts = FenceFacts(
        builds=_builds(4),
        marker=_marker(started_hours_ago=3.0, last_ingest_hours_ago=None, ingests=0),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").reason == "RELAY_IDLE"


def test_missing_marker_is_blind_and_alarms():
    facts = FenceFacts(
        builds=_builds(4),
        marker=MarkerRead(state=None, problem="the relay has not written one", path="/x.json"),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    check = _by_name(report, "relay_idle")
    assert check.reason == "BLIND"
    assert report.status is Status.ALARM


def test_unreadable_builds_directory_is_blind_and_alarms():
    facts = FenceFacts(
        builds=BuildScan(problem="the build receipts directory does not exist", path="/nope"),
        marker=_marker(),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").reason == "BLIND"
    assert report.status is Status.ALARM


def test_receiving_but_failing_is_visible_in_the_words():
    """An operator must be able to tell 'nothing arriving' from 'arriving and failing'."""
    facts = FenceFacts(
        builds=_builds(4),
        marker=_marker(
            last_ingest_hours_ago=None, last_message_hours_ago=1.0, started_hours_ago=200.0
        ),
    )
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").detail["last_message_at"] is not None


# --- acknowledgement -------------------------------------------------------------


def test_live_ack_downgrades_the_alarm_to_held_without_hiding_it():
    ack = AckState(
        present=True,
        active=True,
        reason="waiting on the capture-outcome wiring",
        until=NOW.date() + timedelta(days=5),
        checks=("relay_idle",),
    )
    facts = FenceFacts(builds=_builds(4), marker=_marker(last_ingest_hours_ago=400.0), ack=ack)
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    check = _by_name(report, "relay_idle")
    assert check.status is Status.HELD
    assert report.status is Status.OK
    # Still loud: the line prints, and it says what it is waiting on.
    assert "capture-outcome wiring" in check.message


def test_ack_for_a_different_check_does_not_hold_this_one():
    ack = AckState(
        present=True,
        active=True,
        reason="store migration",
        until=NOW.date() + timedelta(days=2),
        checks=("store_age",),
    )
    facts = FenceFacts(builds=_builds(4), marker=_marker(last_ingest_hours_ago=400.0), ack=ack)
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert _by_name(report, "relay_idle").status is Status.ALARM
    assert report.status is Status.ALARM


def test_rejected_ack_is_reported_in_the_output():
    ack = AckState(present=True, rejected="no 'until' date", checks=("relay_idle",))
    facts = FenceFacts(builds=_builds(4), marker=_marker(last_ingest_hours_ago=400.0), ack=ack)
    report = evaluate(facts, THRESHOLDS, NOW, relay_only=True)
    assert any("ack rejected" in note for note in report.notes)
    assert report.status is Status.ALARM


# --- rendering -------------------------------------------------------------------


@pytest.mark.parametrize(
    "delta,expected",
    [
        (timedelta(seconds=30), "less than 2 minutes"),
        (timedelta(minutes=40), "40 minutes"),
        (timedelta(hours=4), "4 hours"),
        (timedelta(days=9), "9 days"),
    ],
)
def test_ages_are_written_the_way_a_person_would_say_them(delta, expected):
    assert humanise_age(delta) == expected


def test_every_line_is_a_sentence_not_a_code():
    """User surfaces speak human: no internal identifiers as the primary label."""
    facts = FenceFacts(store=_store(age_hours=400), builds=_builds(4), marker=_marker())
    report = evaluate(facts, THRESHOLDS, NOW)
    for line in report.lines():
        assert " " in line
        assert "STORE_STALE" not in line
        assert "RELAY_IDLE" not in line
