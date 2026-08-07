"""Bounded, dated acknowledgement — the pressure valve that cannot become a mute button.

Sometimes a check is truthfully tripped and everybody already knows why (the capture
wiring is not automatic yet; the store is being migrated). The honest answer is a
*dated deferral*, never a silent waiver. So the fence reads one small file:

    ~/.local/state/fleet-memory/liveness-fence.ack
    {"reason": "waiting on the capture-outcome wiring",
     "until": "2026-08-18",
     "checks": ["relay_idle"]}

While that file is present, unexpired, and covers the tripped check, the check prints
as HELD and does not fail the run. Three rules keep it honest:

* **The line still prints and is still recorded.** Held is loud, just not fatal.
* **A missing, unparseable, or over-long ``until`` rejects the whole file** and says
  why, in the output. Never silently honoured, never silently ignored.
* **The 14-day maximum is a module constant, not a setting.** A configurable ceiling
  on a bounded deferral is not a ceiling.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

__all__ = ["ACK_FILENAME", "AckState", "read_ack"]

#: The longest deferral the fence will honour. NOT configurable, by design.
_ACK_MAX_DAYS = 14

ACK_FILENAME = "liveness-fence.ack"


@dataclass(frozen=True)
class AckState:
    """The acknowledgement file's verdict about itself."""

    present: bool = False
    active: bool = False
    reason: str | None = None
    until: date | None = None
    checks: tuple[str, ...] = ()
    rejected: str | None = None
    expired_on: date | None = None
    path: str = ""

    def holds(self, check_name: str) -> bool:
        """True when this ack is live and names ``check_name``."""
        if not self.active:
            return False
        return check_name in self.checks

    def note(self) -> str | None:
        """A plain-language line to print when the ack is not simply working."""
        if self.rejected:
            return f"ack rejected: {self.rejected}"
        if self.expired_on is not None:
            return f"ack expired on {self.expired_on.isoformat()}"
        return None

    def as_dict(self) -> dict:
        """JSON-safe form for the status file."""
        return {
            "present": self.present,
            "active": self.active,
            "reason": self.reason,
            "until": self.until.isoformat() if self.until else None,
            "checks": list(self.checks),
            "rejected": self.rejected,
            "expired_on": self.expired_on.isoformat() if self.expired_on else None,
            "max_days": _ACK_MAX_DAYS,
        }


def read_ack(path: str | os.PathLike[str], *, today: date) -> AckState:
    """Read and judge the acknowledgement file. Never raises.

    Args:
        path: Where the ack file lives.
        today: The current date, injected so the decision is testable and the fence
            never reads a clock inside its own logic.
    """
    resolved = Path(path).expanduser()
    label = str(resolved)
    try:
        raw = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        return AckState(path=label)
    except OSError as exc:
        return AckState(
            present=True,
            rejected=f"the file could not be read ({type(exc).__name__})",
            path=label,
        )

    try:
        data = json.loads(raw)
    except ValueError:
        return AckState(present=True, rejected="the file is not readable JSON", path=label)
    if not isinstance(data, dict):
        return AckState(
            present=True, rejected="the file is not a JSON object", path=label
        )

    reason = data.get("reason") if isinstance(data.get("reason"), str) else None
    checks_raw = data.get("checks")
    checks: tuple[str, ...] = ()
    if isinstance(checks_raw, list):
        checks = tuple(str(c) for c in checks_raw if isinstance(c, str))

    until_raw = data.get("until")
    if not isinstance(until_raw, str) or not until_raw:
        return AckState(
            present=True,
            reason=reason,
            checks=checks,
            rejected="no 'until' date — an acknowledgement without an expiry is a silent waiver",
            path=label,
        )
    try:
        until = date.fromisoformat(until_raw)
    except ValueError:
        return AckState(
            present=True,
            reason=reason,
            checks=checks,
            rejected=f"the 'until' date {until_raw!r} is not a YYYY-MM-DD date",
            path=label,
        )

    if not checks:
        return AckState(
            present=True,
            reason=reason,
            until=until,
            rejected="no 'checks' listed — an acknowledgement must name what it covers",
            path=label,
        )
    if not reason:
        return AckState(
            present=True,
            until=until,
            checks=checks,
            rejected="no 'reason' given — an acknowledgement must say why",
            path=label,
        )

    if (until - today).days > _ACK_MAX_DAYS:
        return AckState(
            present=True,
            reason=reason,
            until=until,
            checks=checks,
            rejected=(
                f"the 'until' date {until.isoformat()} is more than {_ACK_MAX_DAYS} days "
                "away; a deferral that long is not a deferral"
            ),
            path=label,
        )

    if until < today:
        return AckState(
            present=True,
            reason=reason,
            until=until,
            checks=checks,
            expired_on=until,
            path=label,
        )

    return AckState(
        present=True,
        active=True,
        reason=reason,
        until=until,
        checks=checks,
        path=label,
    )
