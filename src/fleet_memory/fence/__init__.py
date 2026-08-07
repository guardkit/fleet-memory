"""The liveness fence — the memory flywheel's "never dark again" guarantee (ladder ⑦).

The flywheel went dark once for a month and nothing said so. Every layer was built
fail-open ("never block the command"), so silence looked exactly like health. This
package is the cure: two checks, run on a timer, that make silence loud.

    (a) STORE MAX-AGE          the newest row in the store is older than the limit
    (b) RELAY-IDLE-WHILE-BUSY  builds finished recently and the relay ingested nothing

Design constraints that shaped this package — do not undo them casually:

* **Nothing here may import** ``fleet_memory.app``. That module builds a NatsBroker
  and registers the JetStream handler at import time; the fence must never touch a
  broker. The dependency set is ``fleet_memory.settings``, this package, ``psycopg``
  and the standard library.
* **Nothing here may use** ``async_store_context``: it runs ``store.setup()`` (DDL —
  a write) and needs embed config. The store read is a raw psycopg query in a
  read-only session.
* **No DSN on argv, ever.** The DSN arrives only as ``FLEET_MEMORY_PG_DSN``. Every
  error string is passed through ``fixture.dsn.scrub_secrets`` and every host label
  through ``sanitize_target``.
* **A fence that cannot see must not report OK.** Missing or corrupt inputs produce
  ``BLIND``, which is an alarm with its own reason — not a quiet pass. Fail-open is
  the disease this rung exists to cure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "BLIND_REASON",
    "CheckResult",
    "FenceError",
    "FenceReport",
    "Status",
]


class FenceError(Exception):
    """Base class for fence errors that are worth naming to an operator."""


class Status(StrEnum):
    """Outcome of one check.

    ``HELD`` is a tripped check covered by an unexpired, in-bounds acknowledgement:
    it still prints and is still recorded, but it does not fail the run. It is a
    dated deferral, never a silent waiver.
    """

    OK = "ok"
    ALARM = "alarm"
    HELD = "held"


#: Reason string used whenever the fence cannot see one of its inputs.
BLIND_REASON = "BLIND"


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict, in machine form and in plain language.

    Attributes:
        name: Stable check name (``store_age``, ``store_age:guardkit``, ``relay_idle``).
            Used by the acknowledgement file and the status JSON; never a primary label
            in the human line.
        status: OK, ALARM, or HELD.
        reason: Short machine reason (``STORE_STALE``, ``RELAY_IDLE``, ``BLIND``, ...),
            empty when the check passed.
        message: The plain-language sentence an operator reads in the journal.
        detail: Extra machine-readable facts for the status file. Never carries a DSN,
            a password, or any environment value.
    """

    name: str
    status: Status
    reason: str = ""
    message: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def tripped(self) -> bool:
        """True when the underlying condition fired (whether or not it is held)."""
        return self.status in (Status.ALARM, Status.HELD)

    def as_dict(self) -> dict:
        """JSON-safe form for the status file."""
        return {
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class FenceReport:
    """The whole run: every check, the thresholds in force, and the overall verdict."""

    status: Status
    checks: tuple[CheckResult, ...]
    thresholds: dict
    checked_at: str
    ack: dict
    notes: tuple[str, ...] = ()

    @property
    def alarms(self) -> tuple[CheckResult, ...]:
        """Checks that fired and were not held."""
        return tuple(c for c in self.checks if c.status is Status.ALARM)

    def lines(self) -> list[str]:
        """One journal-legible line per check, plus the verdict line."""
        out = [f"NOTE   {n}" for n in self.notes]
        out += [f"{c.status.value.upper():<6} {c.message}" for c in self.checks]
        if self.status is Status.ALARM:
            count = len(self.alarms)
            verb = "is" if count == 1 else "are"
            out.append(
                f"VERDICT ALARM — {count} of {len(self.checks)} checks {verb} "
                "unhappy. Memory may be dark; see the lines above."
            )
        else:
            held = sum(1 for c in self.checks if c.status is Status.HELD)
            suffix = f" ({held} acknowledged)" if held else ""
            out.append(f"VERDICT OK — memory is alive{suffix}.")
        return out

    def as_dict(self) -> dict:
        """JSON-safe form written to the durable status file."""
        return {
            "status": self.status.value,
            "checked_at": self.checked_at,
            "checks": [c.as_dict() for c in self.checks],
            "thresholds": self.thresholds,
            "ack": self.ack,
            "notes": list(self.notes),
        }
