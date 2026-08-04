"""Re-index CLI entrypoint: manifest-driven corpus publish, census, audit, parity.

Usage:
    python -m fleet_memory.reindex                  # publish run (report always written)
    python -m fleet_memory.reindex --dry-run        # census only: NO store/NATS connections
    python -m fleet_memory.reindex --audit          # reconcile report vs store + DLQ
    python -m fleet_memory.reindex --parity         # probe-set retrieval health

Publish runs fail LOUD before walking when FLEET_MEMORY_PUBLISH_NATS_URL or
FLEET_MEMORY_CORPUS_MANIFEST is unset — a run with nowhere to publish must not
process 70,000 files first. The audit exits non-zero unless 100% of published
episodes are accounted for (stored or dead-lettered).

Re-running after interruption is safe — deterministic episode_ids and the
writer's idempotent upsert guarantee no duplicates.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from fleet_memory.settings import Settings

# Configure logging to stderr (not stdout)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = "reindex-report.json"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Re-index the deterministic corpus (manifest-driven) and reviewed backfill"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Census only: walk + classify + collide, no store/NATS connections",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Reconcile a run report's published episodes against store + DLQ",
    )
    parser.add_argument(
        "--parity",
        action="store_true",
        help="Run the probe-set retrieval-health report",
    )
    parser.add_argument(
        "--report",
        default=DEFAULT_REPORT_PATH,
        help=f"Run-report JSON the audit reads (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--report-out",
        default=DEFAULT_REPORT_PATH,
        help=f"Where publish runs write the run report (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--out",
        default="parity-candidate-baseline.json",
        help="Where --parity writes the candidate-baseline JSON",
    )
    parser.add_argument(
        "--probe-set",
        default="eval/probe_set.json",
        help="Probe set JSON for --parity (default: eval/probe_set.json)",
    )
    return parser


def _fail_loud_prewalk(settings: Settings, *, need_publish_url: bool) -> None:
    """Fail BEFORE walking when a publish run is misconfigured.

    Raises:
        SystemExit: With a named missing setting (exit code 2)
    """
    if not settings.corpus_manifest:
        print(
            "ERROR: FLEET_MEMORY_CORPUS_MANIFEST is unset — the pipeline walks ONLY "
            "the manifest's reindex-owned directories and refuses to guess.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if need_publish_url and not settings.publish_nats_url:
        print(
            "ERROR: FLEET_MEMORY_PUBLISH_NATS_URL is unset — a publish run has "
            "nowhere to publish. Set it or use --dry-run for a census.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _print_report(report: Any, backfill_count: int | None = None) -> None:
    """Print the run report summary to stdout."""
    print("\n=== Re-Index Run Report ===")
    print(f"Walked: {report.walked_count}")
    print(f"Published: {report.published_count}")
    if backfill_count is not None:
        print(f"Backfill published: {backfill_count}")
    print(f"Skipped (named reasons): {report.skipped_count}")
    print(f"Unparseable: {report.unparseable_count}")
    for kind, count in sorted(report.per_kind_counts.items()):
        print(f"  {kind}: {count}")
    print("=== End Report ===\n")


def _write_report(report: Any, report_out: str) -> None:
    """Write the run report JSON (always written on publish runs)."""
    Path(report_out).write_text(
        json.dumps(report.to_json_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(f"Run report written to {report_out}")


async def run_dry_run(settings: Settings, args: argparse.Namespace) -> int:
    """Census-only run: NO store or NATS connections are made."""
    from fleet_memory.reindex.manifest import load_manifest
    from fleet_memory.reindex.pipeline import reindex_corpus

    _fail_loud_prewalk(settings, need_publish_url=False)

    manifest = load_manifest(settings.corpus_manifest)
    corpus_root = Path(settings.corpus_root)

    report = await reindex_corpus(corpus_root, manifest, publisher=None, store=None)

    print("\n=== Re-Index Census (dry run — nothing published) ===")
    print(f"Walked: {report.walked_count}")
    print(f"Publishable: {report.published_count}")
    print(f"Skipped (named reasons): {report.skipped_count}")
    print(f"Unparseable: {report.unparseable_count}")
    print("=== End Census ===\n")

    _write_report(report, args.report_out)
    return 0


async def run_publish(settings: Settings, args: argparse.Namespace) -> int:
    """Full publish run: corpus + reviewed backfill, report always written."""
    from fleet_memory.reindex import publisher as publisher_module
    from fleet_memory.reindex.backfill import process_backfill_payload
    from fleet_memory.reindex.manifest import load_manifest
    from fleet_memory.reindex.pipeline import reindex_corpus
    from fleet_memory.reindex.publisher import active_publisher
    from fleet_memory.store import async_store_context

    _fail_loud_prewalk(settings, need_publish_url=True)

    manifest = load_manifest(settings.corpus_manifest)
    corpus_root = Path(settings.corpus_root)
    backfill_dir = Path(settings.backfill_dir)

    logger.info(f"Starting re-index: corpus={corpus_root}, backfill={backfill_dir}")

    report = None
    backfill_count = 0
    try:
        async with (
            active_publisher(settings) as publisher,
            async_store_context(settings) as store,
        ):
            report = await reindex_corpus(
                corpus_root, manifest, publisher.publish, store=store
            )
            logger.info(f"Corpus re-index complete: {report.published_count} published")

            # Reviewed backfill rides the same active publisher (single write path)
            if backfill_dir.exists():
                for payload_file in sorted(backfill_dir.rglob("*.json")):
                    await process_backfill_payload(payload_file)
                    backfill_count += 1

            _print_report(report, backfill_count)
            return 0
    except Exception as e:
        logger.error(f"Re-index failed: {e}", exc_info=True)
        print(f"\nERROR: Re-index failed: {e}", file=sys.stderr)
        return 1
    finally:
        # The report JSON is ALWAYS written on publish runs that produced one
        if report is not None:
            _write_report(report, args.report_out)
        # Defensive: active_publisher clears this, but never leave a stale handle
        publisher_module._active_publisher = None


async def run_audit(settings: Settings, args: argparse.Namespace) -> int:
    """Reconcile a run report against the store and DLQ; non-zero unless 100%."""
    from fleet_memory.reindex.audit import audit_published_episodes
    from fleet_memory.reindex.dlq_client import JetStreamDLQClient
    from fleet_memory.store import async_store_context

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"ERROR: run report not found: {report_path}", file=sys.stderr)
        return 2

    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    published_natural_keys = report_data.get("published_natural_keys", [])

    class _ReportStub:
        pass

    stub = _ReportStub()
    stub.published_natural_keys = published_natural_keys

    # One DLQ membership set per project present in the run report
    projects = sorted(
        {key.split(":")[1] for key in published_natural_keys if len(key.split(":")) == 3}
    )

    class _MultiProjectDLQ:
        """Union membership over each project's DLQ subject."""

        def __init__(self, clients: list[JetStreamDLQClient]) -> None:
            self._clients = clients

        async def check_episode_on_dlq(self, episode_id: str) -> bool:
            for client in self._clients:
                if await client.check_episode_on_dlq(episode_id):
                    return True
            return False

    dlq_client = _MultiProjectDLQ(
        [JetStreamDLQClient(settings, project) for project in projects]
    )

    async with async_store_context(settings) as store:
        result = await audit_published_episodes(stub, store, dlq_client)

    print("\n=== Re-Index Audit ===")
    print(f"Published: {result.total_published}")
    print(f"Stored: {result.stored_count}")
    print(f"Dead-lettered: {result.dlq_count}")
    print(f"Unaccounted: {result.unaccounted_count}")
    for natural_key in result.unaccounted_episodes:
        print(f"  UNACCOUNTED: {natural_key}")
    print("=== End Audit ===\n")

    if not result.is_100_percent_accounted:
        print(
            f"ERROR: {result.unaccounted_count} episodes unaccounted for "
            f"(neither stored nor dead-lettered)",
            file=sys.stderr,
        )
        return 1
    return 0


async def run_parity(settings: Settings, args: argparse.Namespace) -> int:
    """Probe-set retrieval-health run; writes the candidate baseline to --out."""
    from fleet_memory.reindex.parity import (
        generate_parity_report,
        load_probe_set,
        write_candidate_baseline,
    )
    from fleet_memory.retrieval.assembly import assemble_context
    from fleet_memory.retrieval.core import search
    from fleet_memory.store import async_store_context

    probe_set = load_probe_set(args.probe_set)

    async with async_store_context(settings) as store:
        report = await generate_parity_report(
            probe_set,
            lambda request: search(request, store),
            assemble_context,
        )

    print("\n=== Probe-Set Parity ===")
    print(f"Probes: {report['total_probes']}")
    print(f"Hits (non-empty context, coverage > 0): {report['hits']}")
    print(f"Hit rate: {report['hit_rate']:.0%}")
    print(f"Baseline diff: {report['baseline_diff']}")
    print("=== End Parity ===\n")

    write_candidate_baseline(report, args.out)
    logger.info(f"Candidate baseline written to {args.out}")
    return 0


async def main(argv: list[str] | None = None) -> int:
    """Main entrypoint for re-index CLI."""
    args = build_arg_parser().parse_args(argv)

    try:
        settings = Settings()
    except Exception as e:
        if args.dry_run:
            # A census never opens the store, embedder, or NATS — the
            # connection fields get inert placeholders so --dry-run runs
            # anywhere the corpus lives, with no deployment env at all.
            try:
                settings = Settings(
                    pg_dsn="postgresql://dry-run-placeholder/none",
                    embed_url="http://dry-run-placeholder.invalid",
                )
            except Exception as e2:
                logger.error(f"Failed to load settings: {e2}")
                print(f"ERROR: Failed to load settings: {e2}", file=sys.stderr)
                return 1
        else:
            logger.error(f"Failed to load settings: {e}")
            print(f"ERROR: Failed to load settings: {e}", file=sys.stderr)
            return 1

    if args.parity:
        return await run_parity(settings, args)
    if args.audit:
        return await run_audit(settings, args)
    if args.dry_run:
        return await run_dry_run(settings, args)
    return await run_publish(settings, args)


def sync_main() -> None:
    """Synchronous wrapper for async main."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    sync_main()
