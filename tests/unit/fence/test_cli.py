"""The command itself: what it exits with, what it prints, what it leaves behind.

No database, no NATS, no live service — the store connection is injected as a fake and
every path is a tmp_path. The exit code is the contract the systemd unit depends on:

    0   alive (or validly acknowledged)      1   alarm (including "cannot see")
    2   configuration problem, named          20  unexpected internal error
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleet_memory.fence import __main__ as cli
from fleet_memory.fence.marker import RelayMarker
from fleet_memory.fence.report import LOG_FILENAME, STATUS_FILENAME

NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
DSN_WITH_PASSWORD = "postgresql://memuser:SUPERSECRET123@db.example.net:5433/fleet_memory"


class _FakeCursor:
    """Answers only the two queries the fence asks; records everything it was given."""

    def __init__(self, rows):
        self._rows = list(rows)
        self.executed: list[str] = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if "max(updated_at)" in sql:
            self._last = self._rows.pop(0) if self._rows else (None, None, 0)
        else:
            self._last = None

    def fetchone(self):
        return self._last


class _FakeConn:
    def __init__(self, rows):
        self.cur = _FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


def _factory(rows, *, fail: Exception | None = None):
    holder: dict = {}

    def connect(dsn):
        holder["dsn"] = dsn
        if fail is not None:
            raise fail
        conn = _FakeConn(rows)
        holder["conn"] = conn
        return conn

    connect.holder = holder  # type: ignore[attr-defined]
    return connect


@pytest.fixture
def env(monkeypatch, tmp_path: Path):
    """A complete, isolated fence environment: state dir, receipts dir, marker."""
    monkeypatch.setenv("FLEET_MEMORY_PG_DSN", DSN_WITH_PASSWORD)
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.invalid:9000")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    marker_path = state_dir / "relay-progress.json"
    return {
        "state_dir": state_dir,
        "receipts": receipts,
        "marker_path": marker_path,
        "argv_base": [
            "--state-dir",
            str(state_dir),
            "--builds-dir",
            str(receipts),
            "--marker",
            str(marker_path),
            "--watch-projects",
            "",
        ],
    }


def _make_builds(directory: Path, count: int, *, hours_ago: float = 24.0) -> None:
    for i in range(count):
        moment = (NOW - timedelta(hours=hours_ago + i)).astimezone()
        (directory / f"build-FEAT-TST{i}-{moment.strftime('%Y%m%d%H%M%S')}").mkdir()


def _make_marker(path: Path, *, ingest_hours_ago: float | None, started_hours_ago: float) -> None:
    payload = {
        "schema": 1,
        "started_at": (NOW - timedelta(hours=started_hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_message_at": None,
        "last_ingest_at": (
            None
            if ingest_hours_ago is None
            else (NOW - timedelta(hours=ingest_hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
        "messages_since_start": 4,
        "ingests_since_start": 4,
        "last_disposition": "ack",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# --- exit codes ------------------------------------------------------------------


def test_everything_healthy_exits_zero(env, capsys):
    _make_builds(env["receipts"], 4)
    _make_marker(env["marker_path"], ingest_hours_ago=2, started_hours_ago=200)
    rows = [(NOW - timedelta(hours=3), NOW - timedelta(hours=3), 3661)]

    code = cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows))
    out = capsys.readouterr().out

    assert code == 0
    assert "VERDICT OK" in out


def test_a_stale_store_exits_one(env, capsys):
    _make_builds(env["receipts"], 4)
    _make_marker(env["marker_path"], ingest_hours_ago=2, started_hours_ago=200)
    rows = [(NOW - timedelta(days=9), NOW - timedelta(days=9), 3661)]

    code = cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows))
    out = capsys.readouterr().out

    assert code == 1
    assert "ALARM" in out
    assert "9 days old" in out


def test_a_missing_marker_exits_one_because_blind_is_not_ok(env, capsys):
    _make_builds(env["receipts"], 4)
    rows = [(NOW - timedelta(hours=1), NOW - timedelta(hours=1), 3661)]

    code = cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows))
    out = capsys.readouterr().out

    assert code == 1
    assert "cannot see the relay's progress marker" in out


def test_an_unreachable_store_exits_one_rather_than_crashing(env, capsys):
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    factory = _factory([], fail=TimeoutError("connection timed out"))

    code = cli.main(env["argv_base"], now=NOW, connection_factory=factory)
    out = capsys.readouterr().out

    assert code == 1
    assert "cannot reach the memory store" in out


def test_a_missing_dsn_exits_two_and_names_the_variable(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("FLEET_MEMORY_PG_DSN", raising=False)
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.invalid:9000")

    code = cli.main(["--state-dir", str(tmp_path)], now=NOW)
    err = capsys.readouterr().err

    assert code == 2
    assert "FLEET_MEMORY_PG_DSN" in err
    assert "no --dsn flag" in err


def test_relay_only_needs_no_dsn_at_all(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("FLEET_MEMORY_PG_DSN", raising=False)
    monkeypatch.setenv("FLEET_MEMORY_EMBED_URL", "http://embed.invalid:9000")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    marker = tmp_path / "relay-progress.json"
    _make_marker(marker, ingest_hours_ago=1, started_hours_ago=100)

    code = cli.main(
        [
            "--relay-only",
            "--state-dir",
            str(tmp_path),
            "--builds-dir",
            str(receipts),
            "--marker",
            str(marker),
        ],
        now=NOW,
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "memory store" not in out  # the store was genuinely not consulted


def test_an_unexpected_internal_error_exits_twenty(env, monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise RuntimeError("something nobody planned for")

    monkeypatch.setattr(cli, "evaluate", boom)
    code = cli.main(env["argv_base"], now=NOW, connection_factory=_factory([(NOW, NOW, 1)]))

    assert code == 20
    assert "unexpected problem" in capsys.readouterr().err


# --- output shapes ---------------------------------------------------------------


def test_json_mode_prints_one_parseable_line(env, capsys):
    _make_builds(env["receipts"], 4)
    _make_marker(env["marker_path"], ingest_hours_ago=2, started_hours_ago=200)
    rows = [(NOW - timedelta(hours=3), NOW - timedelta(hours=3), 3661)]

    code = cli.main(
        [*env["argv_base"], "--json"], now=NOW, connection_factory=_factory(rows)
    )
    out = capsys.readouterr().out.strip()

    assert code == 0
    assert "\n" not in out
    payload = json.loads(out)
    assert payload["status"] == "ok"
    assert payload["thresholds"]["store_max_age_hours"] == 168
    assert {c["name"] for c in payload["checks"]} == {"store_age", "relay_idle"}


def test_store_only_and_relay_only_are_mutually_exclusive(env):
    with pytest.raises(SystemExit) as exc:
        cli.main([*env["argv_base"], "--store-only", "--relay-only"], now=NOW)
    assert exc.value.code == 2


def test_watched_projects_get_their_own_line(env, capsys):
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    rows = [
        (NOW - timedelta(hours=3), NOW - timedelta(hours=3), 3661),  # whole store
        (NOW - timedelta(days=40), NOW - timedelta(days=40), 1200),  # guardkit
    ]
    argv = [a for a in env["argv_base"] if a not in ("--watch-projects", "")]

    code = cli.main(
        [*argv, "--watch-projects", "guardkit"], now=NOW, connection_factory=_factory(rows)
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "memory for guardkit" in out


# --- durable record --------------------------------------------------------------


def test_the_status_file_is_written_on_a_green_run(env):
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    rows = [(NOW - timedelta(hours=1), NOW - timedelta(hours=1), 10)]

    cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows))

    status = json.loads((env["state_dir"] / STATUS_FILENAME).read_text(encoding="utf-8"))
    assert status["status"] == "ok"
    assert status["checked_at"] == NOW.isoformat()
    assert not (env["state_dir"] / LOG_FILENAME).exists()  # green runs do not grow the log


def test_the_status_file_is_written_and_the_log_appended_on_an_alarm(env):
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    rows = [(NOW - timedelta(days=30), NOW - timedelta(days=30), 10)]

    cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows))

    status = json.loads((env["state_dir"] / STATUS_FILENAME).read_text(encoding="utf-8"))
    assert status["status"] == "alarm"
    log = (env["state_dir"] / LOG_FILENAME).read_text(encoding="utf-8")
    assert "30 days old" in log
    assert NOW.isoformat() in log


def test_the_log_is_a_history_it_appends_rather_than_replaces(env):
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    rows_a = [(NOW - timedelta(days=30), NOW - timedelta(days=30), 10)]
    rows_b = [(NOW - timedelta(days=31), NOW - timedelta(days=31), 10)]

    cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows_a))
    cli.main(env["argv_base"], now=NOW + timedelta(hours=4), connection_factory=_factory(rows_b))

    log = (env["state_dir"] / LOG_FILENAME).read_text(encoding="utf-8")
    assert NOW.isoformat() in log
    assert (NOW + timedelta(hours=4)).isoformat() in log


def test_a_live_ack_makes_a_tripped_check_exit_zero_but_still_print(env, capsys):
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    (env["state_dir"] / "liveness-fence.ack").write_text(
        json.dumps(
            {
                "reason": "store migration in progress",
                "until": (NOW.date() + timedelta(days=4)).isoformat(),
                "checks": ["store_age"],
            }
        ),
        encoding="utf-8",
    )
    rows = [(NOW - timedelta(days=30), NOW - timedelta(days=30), 10)]

    code = cli.main(env["argv_base"], now=NOW, connection_factory=_factory(rows))
    out = capsys.readouterr().out

    assert code == 0
    assert "HELD" in out
    assert "store migration in progress" in out


def test_the_fence_asks_for_a_read_only_session_before_anything_else(env):
    """The watchdog must never be able to change what it watches."""
    _make_builds(env["receipts"], 1)
    _make_marker(env["marker_path"], ingest_hours_ago=1, started_hours_ago=200)
    factory = _factory([(NOW, NOW, 10)])

    cli.main(env["argv_base"], now=NOW, connection_factory=factory)

    executed = factory.holder["conn"].cur.executed
    # Order matters: the CURRENT transaction must be marked read-only first — the
    # default-setting alone arrives too late to bind it.
    assert executed[0] == "SET TRANSACTION READ ONLY"
    assert executed[1] == "SET default_transaction_read_only = on"
    assert executed[2] == "SET TIME ZONE 'UTC'"
    assert factory.holder["conn"].closed is True


def test_a_real_relay_marker_is_understood_end_to_end(env, capsys):
    """Written by the producer half, read by the consumer half — one shape, one place."""
    _make_builds(env["receipts"], 4)
    marker = RelayMarker(env["marker_path"])
    marker.record_start()
    marker.record_ingest()
    rows = [(NOW - timedelta(hours=1), NOW - timedelta(hours=1), 10)]

    code = cli.main(
        env["argv_base"], now=datetime.now(UTC), connection_factory=_factory(rows)
    )

    assert code == 0
    assert "relay" in capsys.readouterr().out
