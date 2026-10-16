"""deploy/local's wrappers choose their own Compose project and file.

A ``COMPOSE_PROJECT_NAME`` or ``COMPOSE_FILE`` exported in the calling shell
must not point deploy.sh or smoke.sh at another project (16 October 2026).
Every ``docker`` call the wrappers make is intercepted here by a stand-in
``docker`` first on ``PATH``, which records its arguments and the Compose
settings it was given; no real Docker is used.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

LOCAL = Path(__file__).resolve().parents[2] / "deploy" / "local"

#: Records argv and every COMPOSE_* setting it received, one JSON line per
#: call, then answers the smoke gates' questions as a healthy database would.
_FAKE_DOCKER = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_DOCKER_LOG"], "a") as log:
    log.write(json.dumps({
        "argv": sys.argv[1:],
        "compose_env": {k: v for k, v in os.environ.items() if k.startswith("COMPOSE_")},
    }) + "\\n")
joined = " ".join(sys.argv[1:])
if "pg_extension" in joined:
    print("vector")
elif "PG_VERSION" in joined:
    print("16")
"""

_SOMEONE_ELSES = {
    "COMPOSE_PROJECT_NAME": "someone-elses-postgres",
    "COMPOSE_FILE": "/elsewhere/compose.yaml",
    "COMPOSE_PROFILES": "everything",
}


@pytest.fixture
def wrappers(tmp_path: Path) -> Path:
    copy = tmp_path / "local"
    shutil.copytree(LOCAL, copy, ignore=shutil.ignore_patterns(".env", ".env.deploy"))
    return copy


def _run(script: Path, tmp_path: Path) -> list[dict]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("docker", _FAKE_DOCKER), ("psql", "#!/bin/sh\nexit 0\n")):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "docker-calls.jsonl"
    log.write_text("")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_DOCKER_LOG": str(log),
        **_SOMEONE_ELSES,
    }
    done = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return [json.loads(line) for line in log.read_text().splitlines()]


def _assert_every_call_is_this_folders(calls: list[dict], project: str) -> None:
    assert calls, "the wrapper made no docker call at all"
    for call in calls:
        argv = call["argv"]
        assert argv[0] == "compose", argv
        assert argv[argv.index("--project-name") + 1] == project, argv
        assert argv[argv.index("--file") + 1] == "docker-compose.yml", argv
        assert argv[argv.index("--project-directory") + 1] == ".", argv
        for name, value in _SOMEONE_ELSES.items():
            assert call["compose_env"].get(name) != value, (name, call)


@pytest.mark.parametrize("script", ["deploy.sh", "smoke.sh"])
def test_an_inherited_project_and_file_are_not_used(
    wrappers: Path, tmp_path: Path, script: str
) -> None:
    calls = _run(wrappers / script, tmp_path)
    _assert_every_call_is_this_folders(calls, "local")


@pytest.mark.parametrize("script", ["deploy.sh", "smoke.sh"])
def test_the_folders_own_env_deploy_may_name_the_project(
    wrappers: Path, tmp_path: Path, script: str
) -> None:
    (wrappers / ".env.deploy").write_text(
        "COMPOSE_PROJECT_NAME=fleet-memory-check\nPGPORT=45432\n"
    )
    calls = _run(wrappers / script, tmp_path)
    _assert_every_call_is_this_folders(calls, "fleet-memory-check")
