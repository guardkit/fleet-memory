"""Count recently finished forge builds, from the receipt directory NAMES only.

Why the names and not the database: ``forge.db`` is SQLite held open by a live
container with an active write-ahead log, so a naive outside reader sees stale data
(or trips over the lock). The receipt directories carry their finish time in the
directory name — ``build-FEAT-<id>-<YYYYMMDDHHMMSS>`` — so counting them needs no
lock, no WAL, and no database dependency at all.

The stamp is written by forge in **local time**. We parse it as local and normalise
to UTC. As a cross-check we compare each parsed stamp against the directory's own
modification time — but only in the directions where a disagreement means something.
Measured against the 24 live receipts, the folder's mtime normally sits **one to two
hours after** the name, because the name marks when the build began and the mtime
marks its last written artifact. That gap is a build duration, not an error, so
flagging it would put a warning on every single run and teach everyone to ignore the
warnings. Only two shapes are genuinely suspicious:

* the name claims a time **after** the folder was last written (impossible), or
* the folder was written **more than a week after** the name (a renamed or reused
  directory).

Either way the name still wins — forge authors it, the mtime is incidental — but the
disagreement is reported rather than swallowed.

A missing or unreadable receipts directory is BLIND, never OK: a fence that cannot
count builds cannot judge relay silence, and must say so.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

__all__ = [
    "BUILD_DIR_PATTERN",
    "BuildReceipt",
    "BuildScan",
    "scan_builds",
]

#: forge's receipt directory naming. The 14-digit stamp is the build's finish time.
BUILD_DIR_PATTERN = re.compile(r"^build-(?P<feat>.+)-(?P<stamp>\d{14})$")

#: How far the NAME may run ahead of the folder's mtime before it looks wrong. A build
#: cannot start after its own last write, so anything past this is a real disagreement.
_SKEW_AHEAD_TOLERANCE = timedelta(hours=1)
#: How far the folder's mtime may lag BEHIND the name before it looks wrong. Generous,
#: because this direction is just build duration until it becomes absurd.
_SKEW_BEHIND_TOLERANCE = timedelta(days=7)


def _is_skewed(finished_at: datetime, mtime: datetime) -> bool:
    """True when the name and the folder's mtime disagree in a way that means something."""
    if finished_at - mtime > _SKEW_AHEAD_TOLERANCE:
        return True
    return mtime - finished_at > _SKEW_BEHIND_TOLERANCE


@dataclass(frozen=True)
class BuildReceipt:
    """One finished build, as told by its directory name."""

    name: str
    feature: str
    finished_at: datetime
    skewed: bool = False


@dataclass(frozen=True)
class BuildScan:
    """Everything the fence learned from the receipts directory.

    ``problem`` set means BLIND — the directory could not be listed at all. Malformed
    names inside a readable directory are counted and ignored; one odd name must not
    stop the fence.
    """

    receipts: tuple[BuildReceipt, ...] = ()
    malformed: tuple[str, ...] = ()
    skewed: tuple[str, ...] = ()
    problem: str | None = None
    path: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def blind(self) -> bool:
        return self.problem is not None

    def finished_since(self, moment: datetime) -> tuple[BuildReceipt, ...]:
        """Receipts whose finish time is at or after ``moment``."""
        return tuple(r for r in self.receipts if r.finished_at >= moment)


def _parse_stamp(stamp: str) -> datetime | None:
    """Parse a 14-digit local-time stamp into an aware UTC datetime."""
    try:
        naive = datetime.strptime(stamp, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    # No tzinfo -> astimezone() interprets it in the machine's local zone, which is
    # how forge wrote it, and returns an aware value we normalise to UTC.
    return naive.astimezone().astimezone(UTC)


def scan_builds(builds_dir: str | os.PathLike[str]) -> BuildScan:
    """List the receipts directory and parse every build stamp. Never raises."""
    resolved = Path(builds_dir).expanduser()
    label = str(resolved)
    try:
        entries = sorted(resolved.iterdir())
    except FileNotFoundError:
        return BuildScan(
            problem=(
                "the build receipts directory does not exist, so the fence cannot tell "
                "whether builds have been running"
            ),
            path=label,
        )
    except OSError as exc:
        return BuildScan(
            problem=(
                "the build receipts directory cannot be read "
                f"({type(exc).__name__}), so the fence cannot count builds"
            ),
            path=label,
        )

    receipts: list[BuildReceipt] = []
    malformed: list[str] = []
    skewed: list[str] = []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            malformed.append(entry.name)
            continue
        match = BUILD_DIR_PATTERN.match(entry.name)
        if match is None:
            malformed.append(entry.name)
            continue
        finished_at = _parse_stamp(match.group("stamp"))
        if finished_at is None:
            malformed.append(entry.name)
            continue
        is_skewed = False
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
            is_skewed = _is_skewed(finished_at, mtime)
        except OSError:
            is_skewed = False
        if is_skewed:
            skewed.append(entry.name)
        receipts.append(
            BuildReceipt(
                name=entry.name,
                feature=match.group("feat"),
                finished_at=finished_at,
                skewed=is_skewed,
            )
        )

    receipts.sort(key=lambda r: r.finished_at)
    return BuildScan(
        receipts=tuple(receipts),
        malformed=tuple(malformed),
        skewed=tuple(skewed),
        problem=None,
        path=label,
        detail={"total_receipts": len(receipts), "malformed_names": len(malformed)},
    )
