"""Where the fence leaves its evidence: a status file always, an alarm log on lapses.

Two durable files, both under the fence's state directory:

* ``liveness-fence-status.json`` — always overwritten, atomically. The current
  verdict, every check, the thresholds that were in force, and the acknowledgement
  state. This is what an operator (or a later dashboard) reads to answer "what does
  the fence think right now?".
* ``liveness-fence.log`` — appended **only when the run alarms**, so the file is a
  history of lapses rather than a green-run diary that has to be rotated.

Neither file may ever contain a DSN, a password, or an environment value: host labels
arrive already sanitised, and nothing here reads the environment.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from fleet_memory.fence import FenceReport, Status

__all__ = [
    "LOG_FILENAME",
    "STATUS_FILENAME",
    "append_alarm_log",
    "write_status",
]

STATUS_FILENAME = "liveness-fence-status.json"
LOG_FILENAME = "liveness-fence.log"


def write_status(state_dir: str | os.PathLike[str], report: FenceReport) -> Path:
    """Atomically overwrite the status file. Returns the path written."""
    directory = Path(state_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / STATUS_FILENAME
    text = json.dumps(report.as_dict(), sort_keys=True, indent=2) + "\n"

    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=".fence-status-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def append_alarm_log(
    state_dir: str | os.PathLike[str], report: FenceReport, *, now: datetime
) -> Path | None:
    """Append the plain-language lines to the lapse log — only on ALARM.

    Returns the log path when something was written, ``None`` on a green run.
    """
    if report.status is not Status.ALARM:
        return None
    directory = Path(state_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / LOG_FILENAME
    stamp = now.isoformat()
    body = "".join(f"{stamp}  {line}\n" for line in report.lines())
    with target.open("a", encoding="utf-8") as handle:
        handle.write(body)
    return target
