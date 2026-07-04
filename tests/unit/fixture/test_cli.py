"""Unit tests for scripts/fixture_snapshot.py (TASK-ABL5-005).

No Docker/Postgres: the fleet_memory.fixture package functions are replaced
with recorders, so these tests cover argument parsing, the snapshot-only env
fallback, dispatch, JSON output shape, exit-code mapping, and credential
hygiene of everything the CLI prints. ``verify`` runs against a real on-disk
fixture directory (pure filesystem). The script is loaded via importlib and
driven in-process through ``main(argv)``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from fleet_memory.fixture import (
    FixtureError,
    FixtureManifest,
    InvalidCutDateError,
    ScratchNamespaceError,
    compute_content_hash,
    write_manifest,
)
from fleet_memory.fixture.temporal_cut import CutResult

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "fixture_snapshot.py"

PASSWORD = "S3cr3tPW"
DSN = f"postgresql://runner:{PASSWORD}@runhost:5544/perrun"
TARGET_LABEL = "runhost:5544/perrun"


def _load_cli():
    spec = importlib.util.spec_from_file_location("fixture_snapshot_cli", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


@pytest.fixture(autouse=True)
def _no_ambient_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's real DSN leak into these tests."""
    monkeypatch.delenv(cli.DSN_ENV_VAR, raising=False)


class Recorder:
    """Callable stub that records calls and returns a scripted result."""

    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.result = result
        self.error = error

    def __call__(self, *args: object, **kwargs: object):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


def make_manifest(**overrides: object) -> FixtureManifest:
    data: dict[str, object] = {
        "fixture_id": "v1",
        "created_at": "2026-07-04T00:00:00Z",
        "source_target": TARGET_LABEL,
        "content_hash": "a" * 64,
        "table_row_counts": {
            "store": 5,
            "store_migrations": 4,
            "store_vectors": 5,
            "vector_migrations": 2,
        },
        "null_occurred_at_count": 176,
    }
    data.update(overrides)
    return FixtureManifest(**data)


def single_json_line(out: str) -> dict:
    """Assert stdout is exactly one JSON line and return the parsed object."""
    assert out.endswith("\n") and out.count("\n") == 1, f"not single-line: {out!r}"
    return json.loads(out)


# ---------------------------------------------------------------------------
# snapshot: dispatch, env fallback, JSON output
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_dispatches_with_explicit_source_dsn(self, monkeypatch, capsys, tmp_path):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "create_snapshot", rec)
        rc = cli.main(
            [
                "snapshot",
                "--fixture-id",
                "v1",
                "--source-dsn",
                DSN,
                "--fixtures-root",
                str(tmp_path),
            ]
        )
        assert rc == 0
        assert rec.calls == [((DSN, "v1", tmp_path), {})]

    def test_env_fallback_when_flag_absent(self, monkeypatch, capsys):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "create_snapshot", rec)
        monkeypatch.setenv(cli.DSN_ENV_VAR, DSN)
        rc = cli.main(["snapshot", "--fixture-id", "v1"])
        assert rc == 0
        (args, _kwargs) = rec.calls[0]
        assert args[0] == DSN

    def test_explicit_flag_wins_over_env(self, monkeypatch, capsys):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "create_snapshot", rec)
        monkeypatch.setenv(cli.DSN_ENV_VAR, "postgresql://other:pw@elsewhere:5432/env")
        rc = cli.main(["snapshot", "--fixture-id", "v1", "--source-dsn", DSN])
        assert rc == 0
        assert rec.calls[0][0][0] == DSN

    def test_missing_both_dsn_sources_exits_2(self, monkeypatch, capsys):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "create_snapshot", rec)
        rc = cli.main(["snapshot", "--fixture-id", "v1"])
        assert rc == 2
        assert rec.calls == []
        err = capsys.readouterr().err
        assert "--source-dsn" in err
        assert cli.DSN_ENV_VAR in err

    def test_default_fixtures_root(self, monkeypatch, capsys):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "create_snapshot", rec)
        rc = cli.main(["snapshot", "--fixture-id", "v1", "--source-dsn", DSN])
        assert rc == 0
        assert rec.calls[0][0][2] == Path("eval") / "fixtures"

    def test_json_output_shape(self, monkeypatch, capsys):
        monkeypatch.setattr(cli, "create_snapshot", Recorder(result=make_manifest()))
        rc = cli.main(["snapshot", "--fixture-id", "v1", "--source-dsn", DSN])
        assert rc == 0
        payload = single_json_line(capsys.readouterr().out)
        assert payload == {
            "content_hash": "a" * 64,
            "fixture_id": "v1",
            "null_occurred_at_count": 176,
            "table_row_counts": {
                "store": 5,
                "store_migrations": 4,
                "store_vectors": 5,
                "vector_migrations": 2,
            },
        }


# ---------------------------------------------------------------------------
# verify: real on-disk fixture, hash round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_on_disk(tmp_path: Path) -> tuple[Path, str]:
    """A minimal intact fixture at <tmp_path>/v1; returns (root, content_hash)."""
    fdir = tmp_path / "v1"
    (fdir / "data").mkdir(parents=True)
    (fdir / "schema.sql").write_text("CREATE TABLE store ();\n", encoding="utf-8")
    (fdir / "data" / "store.copy").write_text("k\tv\n", encoding="utf-8")
    content_hash = compute_content_hash(fdir)
    write_manifest(make_manifest(content_hash=content_hash), fdir)
    return tmp_path, content_hash


class TestVerify:
    def test_intact_fixture_exits_0_with_ok_line(self, fixture_on_disk, capsys):
        root, content_hash = fixture_on_disk
        rc = cli.main(["verify", "--fixture-id", "v1", "--fixtures-root", str(root)])
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out == f"fixture v1 OK sha256={content_hash}\n"
        assert captured.err == ""

    def test_tampered_fixture_exits_1_with_both_hashes(self, fixture_on_disk, capsys):
        root, expected = fixture_on_disk
        payload = root / "v1" / "data" / "store.copy"
        payload.write_bytes(payload.read_bytes() + b"tampered")
        actual = compute_content_hash(root / "v1")
        rc = cli.main(["verify", "--fixture-id", "v1", "--fixtures-root", str(root)])
        assert rc == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "v1" in captured.err
        assert expected in captured.err
        assert actual in captured.err

    def test_unknown_fixture_exits_1(self, tmp_path, capsys):
        rc = cli.main(["verify", "--fixture-id", "nope", "--fixtures-root", str(tmp_path)])
        assert rc == 1
        assert "nope" in capsys.readouterr().err

    def test_missing_fixture_id_is_usage_error(self, capsys):
        assert cli.main(["verify"]) == 2


# ---------------------------------------------------------------------------
# restore: explicit target DSN only
# ---------------------------------------------------------------------------


class TestRestore:
    def test_dispatch_and_json_output(self, monkeypatch, capsys, tmp_path):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "restore_fixture", rec)
        rc = cli.main(
            [
                "restore",
                "--fixture-id",
                "v1",
                "--target-dsn",
                DSN,
                "--fixtures-root",
                str(tmp_path),
            ]
        )
        assert rc == 0
        assert rec.calls == [(("v1", DSN, tmp_path), {})]
        payload = single_json_line(capsys.readouterr().out)
        assert payload["fixture_id"] == "v1"
        assert payload["content_hash"] == "a" * 64
        assert payload["table_row_counts"]["store"] == 5

    def test_target_dsn_required_no_env_fallback(self, monkeypatch, capsys):
        rec = Recorder(result=make_manifest())
        monkeypatch.setattr(cli, "restore_fixture", rec)
        monkeypatch.setenv(cli.DSN_ENV_VAR, DSN)
        rc = cli.main(["restore", "--fixture-id", "v1"])
        assert rc == 2
        assert rec.calls == []
        assert "--target-dsn" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cut: CutResult JSON contract for FEAT-ABL-003 / validation scripts
# ---------------------------------------------------------------------------


class TestCut:
    def test_dispatch_and_cut_result_json(self, monkeypatch, capsys):
        rec = Recorder(result=CutResult(excluded_after_cut=2, excluded_null=3, remaining=7))
        monkeypatch.setattr(cli, "apply_temporal_cut", rec)
        rc = cli.main(["cut", "--target-dsn", DSN, "--cut-date", "2026-06-25"])
        assert rc == 0
        assert rec.calls == [((DSN, "2026-06-25"), {"dry_run": False})]
        payload = single_json_line(capsys.readouterr().out)
        assert payload == {"excluded_after_cut": 2, "excluded_null": 3, "remaining": 7}

    def test_dry_run_passes_through(self, monkeypatch, capsys):
        rec = Recorder(result=CutResult(excluded_after_cut=0, excluded_null=176, remaining=41))
        monkeypatch.setattr(cli, "apply_temporal_cut", rec)
        rc = cli.main(["cut", "--target-dsn", DSN, "--cut-date", "2026-06-25", "--dry-run"])
        assert rc == 0
        assert rec.calls == [((DSN, "2026-06-25"), {"dry_run": True})]

    def test_target_dsn_required_no_env_fallback(self, monkeypatch, capsys):
        rec = Recorder(result=CutResult(0, 0, 0))
        monkeypatch.setattr(cli, "apply_temporal_cut", rec)
        monkeypatch.setenv(cli.DSN_ENV_VAR, DSN)
        assert cli.main(["cut", "--cut-date", "2026-06-25"]) == 2
        assert rec.calls == []

    def test_cut_date_required(self, capsys):
        assert cli.main(["cut", "--target-dsn", DSN]) == 2

    def test_invalid_cut_date_maps_to_exit_1(self, monkeypatch, capsys):
        rec = Recorder(error=InvalidCutDateError("unparsable cut value 'garbage'"))
        monkeypatch.setattr(cli, "apply_temporal_cut", rec)
        rc = cli.main(["cut", "--target-dsn", DSN, "--cut-date", "garbage"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "Invalid cut date" in err


# ---------------------------------------------------------------------------
# discard-scratch / list-scratch
# ---------------------------------------------------------------------------


class TestScratch:
    def test_discard_dispatch_and_json(self, monkeypatch, capsys):
        rec = Recorder(result=3)
        monkeypatch.setattr(cli, "discard_scratch", rec)
        rc = cli.main(["discard-scratch", "--target-dsn", DSN, "--rollout-id", "run_01"])
        assert rc == 0
        assert rec.calls == [((DSN, "run_01"), {})]
        payload = single_json_line(capsys.readouterr().out)
        assert payload == {"deleted": 3, "rollout_id": "run_01"}

    def test_discard_invalid_rollout_id_exits_1(self, monkeypatch, capsys):
        rec = Recorder(error=ScratchNamespaceError("rollout id 'Run-1' must match ^[a-z0-9_]+$"))
        monkeypatch.setattr(cli, "discard_scratch", rec)
        rc = cli.main(["discard-scratch", "--target-dsn", DSN, "--rollout-id", "Run-1"])
        assert rc == 1
        assert "Invalid scratch namespace" in capsys.readouterr().err

    def test_discard_requires_target_dsn(self, monkeypatch, capsys):
        rec = Recorder(result=0)
        monkeypatch.setattr(cli, "discard_scratch", rec)
        monkeypatch.setenv(cli.DSN_ENV_VAR, DSN)
        assert cli.main(["discard-scratch", "--rollout-id", "run_01"]) == 2
        assert rec.calls == []

    def test_list_dispatch_and_json(self, monkeypatch, capsys):
        rec = Recorder(result=["scratch_run_01", "scratch_run_02"])
        monkeypatch.setattr(cli, "list_scratch_projects", rec)
        rc = cli.main(["list-scratch", "--target-dsn", DSN])
        assert rc == 0
        assert rec.calls == [((DSN,), {})]
        payload = single_json_line(capsys.readouterr().out)
        assert payload == {"scratch_projects": ["scratch_run_01", "scratch_run_02"]}

    def test_list_requires_target_dsn(self, monkeypatch, capsys):
        rec = Recorder(result=[])
        monkeypatch.setattr(cli, "list_scratch_projects", rec)
        monkeypatch.setenv(cli.DSN_ENV_VAR, DSN)
        assert cli.main(["list-scratch"]) == 2
        assert rec.calls == []


# ---------------------------------------------------------------------------
# exit-code mapping
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_fixture_error_maps_to_1_with_one_stderr_line(self, monkeypatch, capsys):
        message = f"Cannot connect to {TARGET_LABEL}: connection refused"
        monkeypatch.setattr(cli, "restore_fixture", Recorder(error=FixtureError(message)))
        rc = cli.main(["restore", "--fixture-id", "v1", "--target-dsn", DSN])
        assert rc == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == f"error: {message}\n"

    def test_unexpected_exception_is_not_swallowed(self, monkeypatch):
        monkeypatch.setattr(cli, "create_snapshot", Recorder(error=RuntimeError("boom")))
        with pytest.raises(RuntimeError, match="boom"):
            cli.main(["snapshot", "--fixture-id", "v1", "--source-dsn", DSN])

    def test_unknown_subcommand_is_usage_error(self, capsys):
        assert cli.main(["frobnicate"]) == 2

    def test_no_subcommand_is_usage_error(self, capsys):
        assert cli.main([]) == 2

    def test_help_exits_0(self, capsys):
        assert cli.main(["--help"]) == 0
        assert "snapshot" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# credential hygiene: nothing the CLI prints may carry the DSN or password
# ---------------------------------------------------------------------------


def _dispatch_cases() -> list[tuple[str, list[str], object]]:
    return [
        (
            "create_snapshot",
            ["snapshot", "--fixture-id", "v1", "--source-dsn", DSN],
            make_manifest(),
        ),
        (
            "restore_fixture",
            ["restore", "--fixture-id", "v1", "--target-dsn", DSN],
            make_manifest(),
        ),
        (
            "apply_temporal_cut",
            ["cut", "--target-dsn", DSN, "--cut-date", "2026-06-25"],
            CutResult(1, 2, 3),
        ),
        ("discard_scratch", ["discard-scratch", "--target-dsn", DSN, "--rollout-id", "run_01"], 4),
        ("list_scratch_projects", ["list-scratch", "--target-dsn", DSN], ["scratch_run_01"]),
    ]


class TestCredentialHygiene:
    @pytest.mark.parametrize(("attr", "argv", "result"), _dispatch_cases())
    def test_success_output_is_credential_free(self, monkeypatch, capsys, attr, argv, result):
        monkeypatch.setattr(cli, attr, Recorder(result=result))
        assert cli.main(argv) == 0
        captured = capsys.readouterr()
        for stream in (captured.out, captured.err):
            assert PASSWORD not in stream
            assert DSN not in stream

    @pytest.mark.parametrize(("attr", "argv", "result"), _dispatch_cases())
    def test_error_output_is_credential_free(self, monkeypatch, capsys, attr, argv, result):
        # Package errors are sanitized to host:port/db by contract; the CLI
        # must add nothing beyond that message.
        error = FixtureError(f"Cannot connect to {TARGET_LABEL}: connection refused")
        monkeypatch.setattr(cli, attr, Recorder(error=error))
        assert cli.main(argv) == 1
        captured = capsys.readouterr()
        for stream in (captured.out, captured.err):
            assert PASSWORD not in stream
            assert DSN not in stream
        assert TARGET_LABEL in captured.err

    def test_missing_source_dsn_message_is_credential_free(self, monkeypatch, capsys):
        monkeypatch.setenv(cli.DSN_ENV_VAR, "")
        assert cli.main(["snapshot", "--fixture-id", "v1"]) == 2
        captured = capsys.readouterr()
        assert PASSWORD not in captured.err
        assert DSN not in captured.err
