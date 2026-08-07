"""Reading the forge receipt directory — proven against the REAL names.

The anti-fiction law applied to a parser: ``tests/fixtures/forge_receipt_dirnames.txt``
holds the 24 receipt directory names copied verbatim off the live box (names only, no
content). A parser proven against invented names proves nothing about the names it will
actually meet.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleet_memory.fence.builds import BUILD_DIR_PATTERN, scan_builds

REAL_NAMES_FILE = Path(__file__).parent.parent.parent / "fixtures" / "forge_receipt_dirnames.txt"


@pytest.fixture
def real_names() -> list[str]:
    lines = REAL_NAMES_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


@pytest.fixture
def real_receipts_dir(tmp_path: Path, real_names: list[str]) -> Path:
    """The real names, with mtimes set to the shape the live box actually has.

    On the live box each folder's mtime sits roughly an hour after its name, because
    the name marks when the build began and the mtime its last written artifact.
    Recreating that here keeps the skew assertions meaningful instead of accidental.
    """
    directory = tmp_path / "receipts"
    directory.mkdir()
    for name in real_names:
        entry = directory / name
        entry.mkdir()
        stamp = datetime.strptime(name[-14:], "%Y%m%d%H%M%S").astimezone()
        written = (stamp + timedelta(hours=1)).timestamp()
        os.utime(entry, (written, written))
    return directory


def test_the_fixture_holds_the_live_names(real_names):
    """Guards the fixture itself: 24 real directories were captured 2026-08-07."""
    assert len(real_names) == 24
    assert "build-FEAT-153C-20260731091323" in real_names
    assert "build-FEAT-GRO1-20260804065145" in real_names


def test_every_real_name_parses(real_receipts_dir, real_names):
    scan = scan_builds(real_receipts_dir)
    assert not scan.blind
    assert scan.malformed == ()
    assert len(scan.receipts) == len(real_names)


def test_parsed_stamps_round_trip_back_to_the_directory_name(real_receipts_dir):
    """The stamp is local time. Whatever the box's zone, converting back must match."""
    scan = scan_builds(real_receipts_dir)
    for receipt in scan.receipts:
        local = receipt.finished_at.astimezone()
        assert receipt.name.endswith(local.strftime("%Y%m%d%H%M%S"))


def test_feature_id_survives_the_embedded_hyphens(real_receipts_dir):
    """FEAT ids contain hyphens; only the trailing 14 digits are the stamp."""
    scan = scan_builds(real_receipts_dir)
    features = {r.feature for r in scan.receipts}
    assert "FEAT-GRO1" in features
    assert "FEAT-TST1" in features


def test_receipts_come_back_oldest_first(real_receipts_dir):
    scan = scan_builds(real_receipts_dir)
    stamps = [r.finished_at for r in scan.receipts]
    assert stamps == sorted(stamps)


def test_finished_since_selects_the_window(real_receipts_dir):
    scan = scan_builds(real_receipts_dir)
    newest = max(r.finished_at for r in scan.receipts)
    assert len(scan.finished_since(newest)) == 1
    assert len(scan.finished_since(newest - timedelta(days=365))) == len(scan.receipts)


# --- the odd cases ---------------------------------------------------------------


def test_malformed_names_are_counted_and_ignored_never_fatal(tmp_path: Path):
    directory = tmp_path / "receipts"
    directory.mkdir()
    (directory / "build-FEAT-OK01-20260804102430").mkdir()
    (directory / "build-FEAT-NOPE").mkdir()
    (directory / "not-a-build-at-all").mkdir()
    (directory / "build-FEAT-BAD1-20261399999999").mkdir()  # 14 digits, impossible date
    (directory / "loose-file.txt").write_text("ignored", encoding="utf-8")

    scan = scan_builds(directory)
    assert not scan.blind
    assert len(scan.receipts) == 1
    assert set(scan.malformed) == {
        "build-FEAT-NOPE",
        "not-a-build-at-all",
        "build-FEAT-BAD1-20261399999999",
    }


def test_empty_directory_is_readable_and_simply_has_no_builds(tmp_path: Path):
    directory = tmp_path / "receipts"
    directory.mkdir()
    scan = scan_builds(directory)
    assert not scan.blind
    assert scan.receipts == ()


def test_missing_directory_is_blind_not_ok(tmp_path: Path):
    """A fence that cannot count builds must say so, not pass."""
    scan = scan_builds(tmp_path / "does-not-exist")
    assert scan.blind
    assert "does not exist" in scan.problem


def test_unreadable_directory_is_blind_not_a_crash(tmp_path: Path):
    directory = tmp_path / "receipts"
    directory.mkdir()
    (directory / "build-FEAT-OK01-20260804102430").mkdir()
    os.chmod(directory, 0o000)
    try:
        scan = scan_builds(directory)
    finally:
        os.chmod(directory, 0o755)
    if scan.blind:
        assert "cannot be read" in scan.problem
    else:  # running as root, which can read anything — the path is still exercised
        assert len(scan.receipts) == 1


def test_a_folder_written_long_after_its_name_is_recorded_as_skew(tmp_path: Path):
    """The authored name wins over mtime, but the disagreement is not swallowed."""
    directory = tmp_path / "receipts"
    directory.mkdir()
    entry = directory / "build-FEAT-OLD1-20200101000000"
    entry.mkdir()  # mtime is now; the name says 2020
    scan = scan_builds(directory)
    assert scan.skewed == (entry.name,)
    assert scan.receipts[0].skewed is True
    assert scan.receipts[0].finished_at.year == 2020  # the name was trusted


def test_a_name_in_the_future_relative_to_the_folder_is_recorded_as_skew(tmp_path: Path):
    """A build cannot start after its own last write — that means the parse is wrong."""
    directory = tmp_path / "receipts"
    directory.mkdir()
    future = (datetime.now().astimezone() + timedelta(days=2)).strftime("%Y%m%d%H%M%S")
    entry = directory / f"build-FEAT-FUT1-{future}"
    entry.mkdir()
    scan = scan_builds(directory)
    assert scan.skewed == (entry.name,)


def test_a_normal_build_duration_is_not_reported_as_skew(tmp_path: Path):
    """Measured on the live box, folder mtimes sit 1-2 hours after the name, because
    the name marks the start and the mtime the last artifact. Flagging that would put
    a warning on every run and train everyone to ignore warnings."""
    directory = tmp_path / "receipts"
    directory.mkdir()
    started = datetime.now().astimezone() - timedelta(hours=3)
    entry = directory / f"build-FEAT-DUR1-{started.strftime('%Y%m%d%H%M%S')}"
    entry.mkdir()
    finished_writing = (started + timedelta(hours=2)).timestamp()
    os.utime(entry, (finished_writing, finished_writing))

    scan = scan_builds(directory)
    assert scan.skewed == ()
    assert scan.receipts[0].skewed is False


def test_the_real_receipt_names_produce_no_skew_noise(real_receipts_dir):
    """The 24 live names, recreated with fresh mtimes: quiet, as they should be."""
    scan = scan_builds(real_receipts_dir)
    assert scan.skewed == ()


def test_the_pattern_itself_is_anchored():
    """No accidental match on a name that merely contains a build stamp."""
    assert BUILD_DIR_PATTERN.match("build-FEAT-A-20260804102430")
    assert BUILD_DIR_PATTERN.match("xbuild-FEAT-A-20260804102430") is None
    assert BUILD_DIR_PATTERN.match("build-FEAT-A-20260804102430-copy") is None


def test_home_relative_paths_are_expanded(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "forge-state" / "receipts").mkdir(parents=True)
    scan = scan_builds("~/forge-state/receipts")
    assert not scan.blind
    assert scan.path == str(tmp_path / "forge-state" / "receipts")


def test_scan_never_returns_a_naive_datetime(real_receipts_dir):
    """Everything downstream compares against an aware UTC 'now'."""
    scan = scan_builds(real_receipts_dir)
    for receipt in scan.receipts:
        assert receipt.finished_at.tzinfo is not None
        assert receipt.finished_at.utcoffset() == timedelta(0)
        assert receipt.finished_at < datetime.now(UTC) + timedelta(days=1)
