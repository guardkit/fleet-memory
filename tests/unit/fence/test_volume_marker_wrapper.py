"""Boundary tests for the liveness wrapper's opt-in named-volume marker reader."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
WRAPPER = REPO / "ops/fence/liveness-fence-run.sh"
IMAGE_ID = "sha256:" + "8" * 64


@pytest.fixture
def wrapper_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "commands.log"
    log.touch()

    (bin_dir / "uv").write_text(
        """#!/usr/bin/env bash
set -eu
printf 'uv' >>"$WRAPPER_TEST_LOG"
printf ' <%s>' "$@" >>"$WRAPPER_TEST_LOG"
printf '\n' >>"$WRAPPER_TEST_LOG"
marker=''
while [ "$#" -gt 0 ]; do
    if [ "$1" = --marker ]; then marker=$2; break; fi
    shift
done
if [ -n "$marker" ]; then
    printf 'MARKER:'
    cat "$marker"
else
    printf 'DEFAULT\n'
fi
exit "${FAKE_UV_EXIT:-0}"
""",
        encoding="utf-8",
    )
    (bin_dir / "docker").write_text(
        """#!/usr/bin/env bash
set -eu
printf 'docker' >>"$WRAPPER_TEST_LOG"
printf ' <%s>' "$@" >>"$WRAPPER_TEST_LOG"
printf '\n' >>"$WRAPPER_TEST_LOG"
case "$1 $2" in
    'volume inspect')
        [ "${FAKE_VOLUME_EXISTS:-yes}" = yes ]
        ;;
    'image inspect')
        [ "${FAKE_IMAGE_EXISTS:-yes}" = yes ] || exit 1
        printf '%s\n' "${FAKE_RESOLVED_IMAGE_ID:-$FLEET_MEMORY_FENCE_TOOL_IMAGE_ID}"
        ;;
    'run --rm')
        [ "${FAKE_MARKER_READABLE:-yes}" = yes ] || exit 45
        printf '%s' "${FAKE_MARKER_CONTENT:-new-volume-marker}"
        ;;
    *) exit 90 ;;
esac
""",
        encoding="utf-8",
    )
    (bin_dir / "uv").chmod(0o755)
    (bin_dir / "docker").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "PATH": f"{bin_dir}:{env['PATH']}",
            "WRAPPER_TEST_LOG": str(log),
        }
    )
    return env, log


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WRAPPER)],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _enable_volume(env: dict[str, str]) -> None:
    env["FLEET_MEMORY_FENCE_RELAY_MARKER_VOLUME"] = "owned_relay_state"
    env["FLEET_MEMORY_FENCE_TOOL_IMAGE_ID"] = IMAGE_ID


def test_default_mode_keeps_the_existing_host_marker_operation(wrapper_env):
    env, log = wrapper_env

    result = _run(env)

    assert result.returncode == 0
    assert result.stdout == "DEFAULT\n"
    assert log.read_text(encoding="utf-8") == (
        "uv <run> <--no-sync> <python> <-m> <fleet_memory.fence>\n"
    )


def test_volume_mode_reads_with_an_immutable_offline_container_and_cleans_up(wrapper_env):
    env, log = wrapper_env
    _enable_volume(env)
    env["FAKE_MARKER_CONTENT"] = '{"schema":1,"started_at":"2026-09-27T07:00:00Z"}\n'

    result = _run(env)

    assert result.returncode == 0
    assert result.stdout == f"MARKER:{env['FAKE_MARKER_CONTENT']}"
    calls = log.read_text(encoding="utf-8")
    assert "docker <volume> <inspect> <owned_relay_state>" in calls
    assert f"docker <image> <inspect> <--format> <{{{{.Id}}}}> <{IMAGE_ID}>" in calls
    assert "<--network> <none> <--read-only>" in calls
    assert "type=volume,src=owned_relay_state,dst=/relay-state,readonly" in calls
    assert f"<--entrypoint> </bin/cat> <{IMAGE_ID}>" in calls
    uv_call = next(line for line in calls.splitlines() if line.startswith("uv "))
    marker_path = Path(uv_call.rsplit(" <--marker> <", 1)[1][:-1])
    assert not marker_path.exists()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"FLEET_MEMORY_FENCE_TOOL_IMAGE_ID": "relay:latest"}, "not an immutable sha256"),
        ({"FAKE_IMAGE_EXISTS": "no"}, "not present locally"),
    ],
)
def test_bad_tool_image_is_unknown_without_running_the_fence(wrapper_env, extra, message):
    env, log = wrapper_env
    _enable_volume(env)
    env.update(extra)

    result = _run(env)

    assert result.returncode == 1
    assert result.stderr.startswith("UNKNOWN:")
    assert message in result.stderr
    assert not any(line.startswith("uv ") for line in log.read_text().splitlines())


def test_missing_volume_is_inspected_before_any_mount(wrapper_env):
    env, log = wrapper_env
    _enable_volume(env)
    env["FAKE_VOLUME_EXISTS"] = "no"

    result = _run(env)

    assert result.returncode == 1
    assert "UNKNOWN:" in result.stderr
    assert "does not exist" in result.stderr
    calls = log.read_text(encoding="utf-8")
    assert "docker <volume> <inspect> <owned_relay_state>" in calls
    assert "docker <run>" not in calls
    assert not any(line.startswith("uv ") for line in calls.splitlines())


def test_unreadable_volume_marker_never_falls_back_to_an_old_host_marker(wrapper_env):
    env, log = wrapper_env
    _enable_volume(env)
    env["FAKE_MARKER_READABLE"] = "no"
    old_marker = Path(env["XDG_STATE_HOME"]) / "fleet-memory/relay-progress.json"
    old_marker.parent.mkdir(parents=True)
    old_marker.write_text("old-actionable-marker", encoding="utf-8")

    result = _run(env)

    assert result.returncode == 1
    assert "UNKNOWN:" in result.stderr
    assert "missing or unreadable" in result.stderr
    assert "old-actionable-marker" not in result.stdout + result.stderr
    assert not any(line.startswith("uv ") for line in log.read_text().splitlines())
    assert list(old_marker.parent.glob(".relay-progress.*")) == []
