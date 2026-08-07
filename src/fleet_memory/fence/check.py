"""The decision: given the facts, is memory alive? Pure logic, no I/O, no clock.

Everything this module needs arrives as arguments — including ``now`` — so the
judgement is fully testable and the same facts always produce the same verdict.

The table:

    STORE_STALE          the newest row is older than the limit
    STORE_STALE:<proj>   the same, for a watched project
    STORE_UNREACHABLE    the store could not be reached or queried
    STORE_EMPTY          the store has no rows at all
    RELAY_IDLE           enough builds finished recently and memory recorded nothing
    BLIND                the fence cannot see one of its own inputs

Every one of those is an ALARM. There is no "warn only" tier and no fail-open path:
the month-long blackout happened precisely because every layer preferred to stay
quiet when it was unsure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fleet_memory.fence import BLIND_REASON, CheckResult, FenceReport, Status
from fleet_memory.fence.ack import AckState
from fleet_memory.fence.builds import BuildScan
from fleet_memory.fence.marker import MarkerRead
from fleet_memory.fence.store_age import StoreFacts

__all__ = ["FenceFacts", "Thresholds", "evaluate", "humanise_age"]


@dataclass(frozen=True)
class Thresholds:
    """The numbers in force for one run, and the words used to explain them."""

    store_max_age_hours: int = 168
    build_window_hours: int = 72
    min_builds_in_window: int = 3
    relay_restart_grace_minutes: int = 75
    watch_projects: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "store_max_age_hours": self.store_max_age_hours,
            "build_window_hours": self.build_window_hours,
            "min_builds_in_window": self.min_builds_in_window,
            "relay_restart_grace_minutes": self.relay_restart_grace_minutes,
            "watch_projects": list(self.watch_projects),
        }


@dataclass(frozen=True)
class FenceFacts:
    """Everything gathered this run. ``None`` means "that check was not asked for"."""

    store: StoreFacts | None = None
    builds: BuildScan | None = None
    marker: MarkerRead | None = None
    ack: AckState = field(default_factory=AckState)


def humanise_age(delta: timedelta) -> str:
    """A short, plain-language age: '40 minutes', '4 hours', '9 days'."""
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 90:
        return "less than 2 minutes"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes} minutes"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hours"
    return f"{hours // 24} days"


def _limit_phrase(hours: int) -> str:
    if hours % 24 == 0 and hours >= 24:
        days = hours // 24
        return f"{days} day" if days == 1 else f"{days} days"
    return f"{hours} hour" if hours == 1 else f"{hours} hours"


def _store_check(facts: StoreFacts, thresholds: Thresholds, now: datetime) -> list[CheckResult]:
    if not facts.reachable:
        return [
            CheckResult(
                name="store_age",
                status=Status.ALARM,
                reason="STORE_UNREACHABLE",
                message=(
                    f"memory store: {facts.problem}. Nothing can be written or read "
                    "while this is true, so memory is effectively dark."
                ),
                detail={"target": facts.target},
            )
        ]

    results: list[CheckResult] = []
    limit = _limit_phrase(thresholds.store_max_age_hours)

    if facts.row_count == 0:
        results.append(
            CheckResult(
                name="store_age",
                status=Status.ALARM,
                reason="STORE_EMPTY",
                message=(
                    f"memory store: there is nothing in it at all (0 rows at "
                    f"{facts.target}). Either this is the wrong database or the store "
                    "has been emptied."
                ),
                detail={"target": facts.target, "row_count": 0},
            )
        )
        return results

    newest = facts.newest_updated_at
    if newest is None:
        results.append(
            CheckResult(
                name="store_age",
                status=Status.ALARM,
                reason=BLIND_REASON,
                message=(
                    f"memory store: {facts.row_count} rows are present but none carry a "
                    "write time, so the fence cannot tell how fresh memory is."
                ),
                detail={"target": facts.target, "row_count": facts.row_count},
            )
        )
    else:
        age = now - newest
        common = {
            "target": facts.target,
            "row_count": facts.row_count,
            "newest_updated_at": newest.isoformat(),
            "newest_created_at": (
                facts.newest_created_at.isoformat() if facts.newest_created_at else None
            ),
            "age_hours": round(age.total_seconds() / 3600.0, 2),
        }
        if age > timedelta(hours=thresholds.store_max_age_hours):
            results.append(
                CheckResult(
                    name="store_age",
                    status=Status.ALARM,
                    reason="STORE_STALE",
                    message=(
                        "memory store: the newest thing memory learned is "
                        f"{humanise_age(age)} old (limit {limit})."
                    ),
                    detail=common,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="store_age",
                    status=Status.OK,
                    message=(
                        f"memory store: newest row {humanise_age(age)} old, "
                        f"{facts.row_count} rows in total."
                    ),
                    detail=common,
                )
            )

    for project in facts.per_project:
        name = f"store_age:{project.project}"
        if project.row_count == 0:
            results.append(
                CheckResult(
                    name=name,
                    status=Status.ALARM,
                    reason="STORE_EMPTY",
                    message=(
                        f"memory for {project.project}: nothing is stored under this "
                        "project at all."
                    ),
                    detail={"project": project.project, "row_count": 0},
                )
            )
            continue
        pnewest = project.newest_updated_at
        if pnewest is None:
            results.append(
                CheckResult(
                    name=name,
                    status=Status.ALARM,
                    reason=BLIND_REASON,
                    message=(
                        f"memory for {project.project}: rows are present but none carry "
                        "a write time, so their freshness cannot be judged."
                    ),
                    detail={"project": project.project, "row_count": project.row_count},
                )
            )
            continue
        page = now - pnewest
        pdetail = {
            "project": project.project,
            "row_count": project.row_count,
            "newest_updated_at": pnewest.isoformat(),
            "age_hours": round(page.total_seconds() / 3600.0, 2),
        }
        if page > timedelta(hours=thresholds.store_max_age_hours):
            results.append(
                CheckResult(
                    name=name,
                    status=Status.ALARM,
                    reason="STORE_STALE",
                    message=(
                        f"memory for {project.project}: the newest thing learned is "
                        f"{humanise_age(page)} old (limit {limit})."
                    ),
                    detail=pdetail,
                )
            )
        else:
            results.append(
                CheckResult(
                    name=name,
                    status=Status.OK,
                    message=(
                        f"memory for {project.project}: newest row "
                        f"{humanise_age(page)} old, {project.row_count} rows."
                    ),
                    detail=pdetail,
                )
            )

    return results


def _relay_check(
    builds: BuildScan | None,
    marker: MarkerRead | None,
    thresholds: Thresholds,
    now: datetime,
) -> CheckResult:
    if marker is None or marker.blind:
        problem = marker.problem if marker is not None else "the progress marker was not read"
        return CheckResult(
            name="relay_idle",
            status=Status.ALARM,
            reason=BLIND_REASON,
            message=(
                f"relay: the fence cannot see the relay's progress marker — {problem}. "
                "Until it can, it cannot tell a working relay from a dead one."
            ),
            detail={"marker_path": marker.path if marker else ""},
        )
    if builds is None or builds.blind:
        problem = builds.problem if builds is not None else "the build receipts were not read"
        return CheckResult(
            name="relay_idle",
            status=Status.ALARM,
            reason=BLIND_REASON,
            message=f"relay: {problem}.",
            detail={"builds_dir": builds.path if builds else ""},
        )

    state = marker.state
    assert state is not None  # marker.blind is False, so state is set
    window_start = now - timedelta(hours=thresholds.build_window_hours)
    in_window = builds.finished_since(window_start)
    window_days = thresholds.build_window_hours / 24.0
    window_phrase = (
        f"{int(window_days)} days" if window_days.is_integer() else
        f"{thresholds.build_window_hours} hours"
    )

    last_ingest = state.last_ingest_at
    last_message = state.last_message_at
    detail = {
        "builds_in_window": len(in_window),
        "min_builds_in_window": thresholds.min_builds_in_window,
        "window_start": window_start.isoformat(),
        "relay_started_at": state.started_at.isoformat() if state.started_at else None,
        "last_ingest_at": last_ingest.isoformat() if last_ingest else None,
        "last_message_at": last_message.isoformat() if last_message else None,
        "ingests_since_start": state.ingests_since_start,
        "messages_since_start": state.messages_since_start,
        "last_disposition": state.last_disposition,
        "malformed_receipt_names": len(builds.malformed),
        "skewed_receipt_names": list(builds.skewed),
    }

    def _relay_activity_phrase() -> str:
        if last_ingest is None:
            base = "the relay has recorded no writes since it started"
        else:
            base = f"last write {humanise_age(now - last_ingest)} ago"
        if last_message is not None and (last_ingest is None or last_message > last_ingest):
            base += (
                f", but it did receive a message {humanise_age(now - last_message)} ago "
                f"(outcome: {state.last_disposition or 'unknown'})"
            )
        return base

    if len(in_window) < thresholds.min_builds_in_window:
        return CheckResult(
            name="relay_idle",
            status=Status.OK,
            message=(
                f"relay: only {len(in_window)} builds finished in the last "
                f"{window_phrase}, which is too few to judge silence by. "
                f"{_relay_activity_phrase().capitalize()}."
            ),
            detail=detail,
        )

    if last_ingest is not None and last_ingest >= window_start:
        return CheckResult(
            name="relay_idle",
            status=Status.OK,
            message=(
                f"relay: {len(in_window)} builds finished in the last {window_phrase} "
                f"and memory recorded work too ({_relay_activity_phrase()}, "
                f"{state.ingests_since_start} writes since the relay started)."
            ),
            detail=detail,
        )

    if state.started_at is not None:
        grace_end = state.started_at + timedelta(minutes=thresholds.relay_restart_grace_minutes)
        if now < grace_end:
            detail["grace_until"] = grace_end.isoformat()
            return CheckResult(
                name="relay_idle",
                status=Status.OK,
                reason="RELAY_RESTART_GRACE",
                message=(
                    "relay: it restarted "
                    f"{humanise_age(now - state.started_at)} ago and has not caught up "
                    f"yet. Silence is expected for up to "
                    f"{thresholds.relay_restart_grace_minutes} minutes after a restart, "
                    "so this is not being treated as an alarm."
                ),
                detail=detail,
            )

    return CheckResult(
        name="relay_idle",
        status=Status.ALARM,
        reason="RELAY_IDLE",
        message=(
            f"relay idle: {len(in_window)} builds finished in the last {window_phrase} "
            "and memory recorded nothing. Either the relay is not consuming, or the "
            "close ritual that writes build outcomes did not run (that write is not "
            "yet automatic)."
        ),
        detail=detail,
    )


def _apply_ack(check: CheckResult, ack: AckState) -> CheckResult:
    """Downgrade a tripped check to HELD when a live acknowledgement names it."""
    if check.status is not Status.ALARM or not ack.holds(check.name):
        return check
    until = ack.until.isoformat() if ack.until else "an unstated date"
    return CheckResult(
        name=check.name,
        status=Status.HELD,
        reason=check.reason,
        message=f"{check.message} Acknowledged until {until}: {ack.reason}.",
        detail={**check.detail, "acknowledged_until": until, "acknowledged_reason": ack.reason},
    )


def evaluate(
    facts: FenceFacts,
    thresholds: Thresholds,
    now: datetime,
    *,
    store_only: bool = False,
    relay_only: bool = False,
) -> FenceReport:
    """Turn facts into a verdict. Pure: no clock, no filesystem, no database."""
    checks: list[CheckResult] = []

    if not relay_only:
        if facts.store is None:
            checks.append(
                CheckResult(
                    name="store_age",
                    status=Status.ALARM,
                    reason=BLIND_REASON,
                    message=(
                        "memory store: the fence was not able to look at the store at "
                        "all, so it cannot say whether memory is fresh."
                    ),
                )
            )
        else:
            checks.extend(_store_check(facts.store, thresholds, now))

    if not store_only:
        checks.append(_relay_check(facts.builds, facts.marker, thresholds, now))

    checks = [_apply_ack(c, facts.ack) for c in checks]
    status = Status.ALARM if any(c.status is Status.ALARM for c in checks) else Status.OK

    notes: list[str] = []
    ack_note = facts.ack.note()
    if ack_note:
        notes.append(ack_note)
    if facts.builds is not None and facts.builds.skewed:
        notes.append(
            "some build receipt names disagree with the folder's own modification "
            f"time by more than an hour ({len(facts.builds.skewed)} of them); the name "
            "was trusted, as forge authors it"
        )

    return FenceReport(
        status=status,
        checks=tuple(checks),
        thresholds=thresholds.as_dict(),
        checked_at=now.isoformat(),
        ack=facts.ack.as_dict(),
        notes=tuple(notes),
    )
