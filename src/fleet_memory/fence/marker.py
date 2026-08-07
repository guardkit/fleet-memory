"""The relay's progress marker — the only place the file's shape is defined.

Why this exists at all: a clean relay ingest is completely silent. ``RelayService.ingest``
logs nothing on success, and the handler logs only failures, so "the relay is working"
and "the relay is dead" look identical from outside. The only true progress signal is
the JetStream durable consumer's position — and reading that means connecting to the
broker, which the standing broker-isolation law forbids. So the relay mints its own
marker instead: one small JSON file, replaced atomically, modelled on the Chronicler's
watermark.

**The write must never break ingestion.** Every public method swallows every exception
and returns. An ack must never depend on a filesystem write — a full disk or a
read-only mount is a reason for the fence to go BLIND, never a reason to lose a message.

Both halves of the fence live here (the one-rule law): the relay writes through
:class:`RelayMarker`, the checker reads through :func:`read_marker`. Neither restates
the field names.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "MARKER_SCHEMA",
    "MarkerRead",
    "MarkerState",
    "RelayMarker",
    "read_marker",
]

logger = logging.getLogger(__name__)

#: Bump only on an incompatible field change; the reader tolerates unknown versions.
MARKER_SCHEMA = 1


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: object) -> datetime | None:
    """Parse a marker timestamp into an aware UTC datetime; None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class MarkerState:
    """What the relay last told us about itself."""

    started_at: datetime | None
    last_message_at: datetime | None
    last_ingest_at: datetime | None
    messages_since_start: int
    ingests_since_start: int
    last_disposition: str | None


@dataclass(frozen=True)
class MarkerRead:
    """Result of reading the marker: a state, or a plain-language reason it is missing.

    ``problem`` being set is what makes the fence BLIND. It is never an exception —
    the checker must always be able to finish and write its status file.
    """

    state: MarkerState | None
    problem: str | None
    path: str

    @property
    def blind(self) -> bool:
        return self.state is None


class RelayMarker:
    """Best-effort progress marker written by the relay after every message.

    In-process counters (``messages_since_start`` / ``ingests_since_start``) reset on
    :meth:`record_start`; the ``last_*`` timestamps are preserved across a restart by
    reading the file first, so a container recreate does not erase the history the
    fence judges on.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._started_at: str | None = None
        self._last_message_at: str | None = None
        self._last_ingest_at: str | None = None
        self._last_disposition: str | None = None
        self._messages = 0
        self._ingests = 0
        self._warned = False

    # --- writer side -----------------------------------------------------------

    def record_start(self) -> None:
        """Stamp a new start, preserving whatever the previous process left behind."""
        prior = read_marker(self.path).state
        if prior is not None:
            self._last_message_at = _iso_or_none(prior.last_message_at)
            self._last_ingest_at = _iso_or_none(prior.last_ingest_at)
            self._last_disposition = prior.last_disposition
        self._started_at = _now_iso()
        self._messages = 0
        self._ingests = 0
        self._write()

    def record_ingest(self) -> None:
        """A message was ingested and committed — the signal the idle check reads."""
        stamp = _now_iso()
        self._ingests += 1
        self._messages += 1
        self._last_ingest_at = stamp
        self._last_message_at = stamp
        self._last_disposition = "ack"
        self._write()

    def record_message(self, *, disposition: str) -> None:
        """A message arrived but did not become an ingest (dlq / nak / ...).

        Recorded separately from ingests so an operator can tell "receiving but
        failing" from "receiving nothing" at a glance.
        """
        self._messages += 1
        self._last_message_at = _now_iso()
        self._last_disposition = disposition
        self._write()

    # --- internals -------------------------------------------------------------

    def _payload(self) -> dict:
        return {
            "schema": MARKER_SCHEMA,
            "started_at": self._started_at,
            "last_message_at": self._last_message_at,
            "last_ingest_at": self._last_ingest_at,
            "messages_since_start": self._messages,
            "ingests_since_start": self._ingests,
            "last_disposition": self._last_disposition,
        }

    def _write(self) -> None:
        """Atomically replace the marker file. Never raises, never blocks an ack."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(self._payload(), sort_keys=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=".relay-progress-", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(text + "\n")
                os.replace(tmp_name, self.path)
            except Exception:
                _quiet_unlink(tmp_name)
                raise
        except Exception as exc:  # never let a filesystem problem cost a message
            if not self._warned:
                self._warned = True
                logger.warning(
                    "Relay progress marker could not be written (%s); ingestion is "
                    "unaffected, but the liveness fence will report BLIND until this "
                    "is fixed. Further failures are not logged.",
                    type(exc).__name__,
                )


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quiet_unlink(name: str) -> None:
    try:
        os.unlink(name)
    except OSError:
        pass


def read_marker(path: str | os.PathLike[str]) -> MarkerRead:
    """Read the marker tolerantly: absent, truncated, or corrupt all become BLIND.

    Never raises. A fence that crashes on a half-written file is a fence that stops
    watching, which is exactly the failure this rung exists to prevent.
    """
    resolved = Path(path).expanduser()
    label = str(resolved)
    try:
        raw = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        return MarkerRead(
            None,
            "the relay has not written one yet; either it has not been rebuilt with "
            "the fence, or its state directory is not mounted",
            label,
        )
    except OSError as exc:
        return MarkerRead(None, f"the progress marker cannot be read ({type(exc).__name__})", label)

    try:
        data = json.loads(raw)
    except ValueError:
        return MarkerRead(
            None,
            "the progress marker is not readable JSON (truncated or corrupt)",
            label,
        )
    if not isinstance(data, dict):
        return MarkerRead(None, "the progress marker is not in the expected shape", label)

    started_at = _parse_iso(data.get("started_at"))
    if started_at is None:
        return MarkerRead(
            None,
            "the progress marker carries no start time, so the relay's state is unknown",
            label,
        )

    state = MarkerState(
        started_at=started_at,
        last_message_at=_parse_iso(data.get("last_message_at")),
        last_ingest_at=_parse_iso(data.get("last_ingest_at")),
        messages_since_start=_int_or_zero(data.get("messages_since_start")),
        ingests_since_start=_int_or_zero(data.get("ingests_since_start")),
        last_disposition=(
            data.get("last_disposition") if isinstance(data.get("last_disposition"), str) else None
        ),
    )
    return MarkerRead(state, None, label)


def _int_or_zero(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
