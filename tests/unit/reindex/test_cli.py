"""Tests for the re-index CLI entrypoint.

Pins the fail-loud-before-walking contract (a publish run with nowhere to
publish must not process 70,000 files first), the connectionless --dry-run,
and the audit exit code.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import fleet_memory.reindex.__main__ as cli

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def _settings(**overrides) -> MagicMock:
    settings = MagicMock()
    settings.publish_nats_url = overrides.get("publish_nats_url", "nats://pub:4222")
    settings.corpus_manifest = overrides.get(
        "corpus_manifest", str(FIXTURES_DIR / "corpus_manifest.json")
    )
    settings.corpus_root = overrides.get("corpus_root", str(FIXTURES_DIR / "corpus"))
    settings.backfill_dir = overrides.get("backfill_dir", "nonexistent-backfill/")
    settings.nats_url = "nats://consumer:4222"
    settings.dlq_subject = "memory.dlq"
    return settings


def _args(**overrides) -> MagicMock:
    args = MagicMock()
    args.report_out = overrides.get("report_out", "reindex-report.json")
    args.report = overrides.get("report", "reindex-report.json")
    args.out = overrides.get("out", "candidate.json")
    args.probe_set = overrides.get("probe_set", "eval/probe_set.json")
    return args


class TestFailLoudPreWalk:
    """Misconfigured publish runs die BEFORE the walker is ever called."""

    async def test_missing_publish_url_exits_before_walking(self, tmp_path: Path) -> None:
        settings = _settings(publish_nats_url="")

        with patch("fleet_memory.reindex.pipeline.walk_roots") as mock_walk:
            with pytest.raises(SystemExit) as exc_info:
                await cli.run_publish(settings, _args(report_out=str(tmp_path / "r.json")))

        assert exc_info.value.code == 2
        mock_walk.assert_not_called()

    async def test_missing_corpus_manifest_exits_before_walking(
        self, tmp_path: Path
    ) -> None:
        settings = _settings(corpus_manifest="")

        with patch("fleet_memory.reindex.pipeline.walk_roots") as mock_walk:
            with pytest.raises(SystemExit) as exc_info:
                await cli.run_publish(settings, _args(report_out=str(tmp_path / "r.json")))

        assert exc_info.value.code == 2
        mock_walk.assert_not_called()

    async def test_dry_run_still_requires_manifest(self, tmp_path: Path) -> None:
        settings = _settings(corpus_manifest="")

        with patch("fleet_memory.reindex.pipeline.walk_roots") as mock_walk:
            with pytest.raises(SystemExit) as exc_info:
                await cli.run_dry_run(settings, _args(report_out=str(tmp_path / "r.json")))

        assert exc_info.value.code == 2
        mock_walk.assert_not_called()


class TestDryRunConnectionless:
    """--dry-run needs NO store or NATS connections."""

    async def test_dry_run_census_over_fixture_corpus(self, tmp_path: Path) -> None:
        report_out = tmp_path / "census.json"
        settings = _settings()

        with (
            patch("fleet_memory.store.async_store_context") as mock_store_ctx,
            patch("fleet_memory.reindex.publisher.ReindexPublisher") as mock_publisher,
        ):
            exit_code = await cli.run_dry_run(
                settings, _args(report_out=str(report_out))
            )

        assert exit_code == 0
        mock_store_ctx.assert_not_called()
        mock_publisher.assert_not_called()

        # Census over the verbatim fixture corpus: 10 files under
        # tasks/completed, 5 publishable, 5 skipped with named reasons
        report = json.loads(report_out.read_text(encoding="utf-8"))
        assert report["walked_count"] == 10
        assert report["published_count"] == 5
        assert report["skipped_count"] == 5
        assert report["unparseable_count"] == 0
        assert report["walked_count"] == (
            report["published_count"]
            + report["skipped_count"]
            + report["unparseable_count"]
        )
        assert (
            "build_outcome:guardkit:TASK_FIX_RESUMEVENV01"
            in report["published_natural_keys"]
        )


class TestAuditExitCode:
    """Audit exits non-zero unless 100% accounted."""

    async def test_missing_report_file_exits_nonzero(self, tmp_path: Path) -> None:
        settings = _settings()
        exit_code = await cli.run_audit(
            settings, _args(report=str(tmp_path / "missing.json"))
        )
        assert exit_code == 2

    async def test_unaccounted_episode_exits_nonzero(self, tmp_path: Path) -> None:
        report_path = tmp_path / "report.json"
        report_path.write_text(
            json.dumps(
                {"published_natural_keys": ["build_outcome:guardkit:TASK_GONE"]}
            ),
            encoding="utf-8",
        )
        settings = _settings()

        # Store has nothing; DLQ has nothing -> unaccounted -> non-zero
        class _EmptyStore:
            async def aget(self, namespace, key):
                return None

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_store_ctx(settings):
            yield _EmptyStore()

        with (
            patch("fleet_memory.store.async_store_context", fake_store_ctx),
            patch(
                "fleet_memory.reindex.dlq_client.JetStreamDLQClient"
            ) as mock_dlq_class,
        ):
            mock_dlq = mock_dlq_class.return_value

            async def never_on_dlq(episode_id):
                return False

            mock_dlq.check_episode_on_dlq = never_on_dlq

            exit_code = await cli.run_audit(settings, _args(report=str(report_path)))

        assert exit_code == 1

    async def test_fully_accounted_exits_zero(self, tmp_path: Path) -> None:
        natural_key = "build_outcome:guardkit:TASK_OK"
        report_path = tmp_path / "report.json"
        report_path.write_text(
            json.dumps({"published_natural_keys": [natural_key]}), encoding="utf-8"
        )
        settings = _settings()

        from fleet_memory.writer.identity import record_identity

        stored_key = str(record_identity(natural_key))

        class _Store:
            async def aget(self, namespace, key):
                if namespace == ("fleet_memory", "guardkit", "build_outcome"):
                    if key == stored_key:
                        return {"value": {}}
                return None

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_store_ctx(settings):
            yield _Store()

        with patch("fleet_memory.store.async_store_context", fake_store_ctx):
            exit_code = await cli.run_audit(settings, _args(report=str(report_path)))

        assert exit_code == 0


class TestArgParser:
    """CLI flags exist and default sanely."""

    def test_flags(self) -> None:
        parser = cli.build_arg_parser()
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.audit is False
        assert args.parity is False
        assert args.report_out == "reindex-report.json"

        args = parser.parse_args(
            ["--dry-run", "--report-out", "out.json", "--out", "cb.json"]
        )
        assert args.dry_run is True
        assert args.report_out == "out.json"
        assert args.out == "cb.json"


class TestDryRunNeedsNoDeploymentEnv:
    """A census must run with NO store/embed/NATS env at all (coach minor #2)."""

    def test_dry_run_without_pg_dsn_or_embed_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        for name in (
            "FLEET_MEMORY_PG_DSN",
            "FLEET_MEMORY_EMBED_URL",
            "FLEET_MEMORY_NATS_URL",
            "FLEET_MEMORY_PUBLISH_NATS_URL",
        ):
            monkeypatch.delenv(name, raising=False)
        corpus = tmp_path / "corpus"
        (corpus / "tasks" / "completed").mkdir(parents=True)
        manifest_src = Path(str(FIXTURES_DIR / "corpus_manifest.json"))
        manifest = tmp_path / "manifest.json"
        manifest.write_text(manifest_src.read_text())
        monkeypatch.setenv("FLEET_MEMORY_CORPUS_MANIFEST", str(manifest))
        monkeypatch.setenv("FLEET_MEMORY_CORPUS_ROOT", str(corpus))
        monkeypatch.chdir(tmp_path)  # no repo .env can leak in

        exit_code = asyncio.run(cli.main(["--dry-run"]))

        assert exit_code == 0
        assert "Walked" in capsys.readouterr().out
