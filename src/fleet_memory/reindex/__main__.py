"""Re-index CLI entrypoint for deterministic corpus + reviewed backfill.

Usage:
    python -m fleet_memory.reindex

Runs a full re-index:
1. Walks deterministic corpus (TASK-RIP-005)
2. Processes reviewed backfill payloads (TASK-RIP-006)
3. Prints RunReport
4. Exits non-zero on failure (fail-loud)

Re-running after interruption is safe — downstream idempotent upsert
guarantees no duplicates from documents published before interruption.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from fleet_memory.reindex.backfill import process_backfill_payload
from fleet_memory.reindex.pipeline import RunReport, reindex_corpus
from fleet_memory.reindex.publisher import publish_episode
from fleet_memory.settings import Settings
from fleet_memory.store import async_store_context

# Configure logging to stderr (not stdout)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


async def process_backfill(
    backfill_dir: Path,
    publisher,
) -> int:
    """Walk backfill directory and process reviewed payloads.

    Args:
        backfill_dir: Directory containing backfill staging payloads
        publisher: Publisher function to use for reviewed payloads

    Returns:
        Number of payloads processed (published)

    Raises:
        Exception: Any processing errors are propagated (fail-loud)
    """
    published_count = 0

    # Walk backfill directory for .json files
    if not backfill_dir.exists():
        logger.info(f"Backfill directory does not exist: {backfill_dir}")
        return 0

    for payload_file in backfill_dir.rglob("*.json"):
        # process_backfill_payload has its own review gate check
        await process_backfill_payload(payload_file)
        published_count += 1
        logger.info(f"Processed backfill payload: {payload_file}")

    return published_count


def print_report(corpus_report: RunReport, backfill_count: int) -> None:
    """Print the re-index run report to stdout.

    Args:
        corpus_report: RunReport from corpus re-index
        backfill_count: Number of backfill payloads published
    """
    print("\n=== Re-Index Run Report ===")
    print(f"Corpus published: {corpus_report.published_count}")
    print(f"Backfill published: {backfill_count}")
    print(f"Unparseable: {corpus_report.unparseable_count}")
    print(f"Unrecognized: {corpus_report.unrecognized_count}")

    if corpus_report.unparseable:
        print("\nUnparseable documents:")
        for item in corpus_report.unparseable:
            print(f"  - {item['path']}: {item['reason']}")

    if corpus_report.unrecognized:
        print("\nUnrecognized documents:")
        for item in corpus_report.unrecognized:
            print(f"  - {item['path']}: {item['reason']}")

    total_published = corpus_report.published_count + backfill_count
    total_docs = (
        total_published
        + corpus_report.unparseable_count
        + corpus_report.unrecognized_count
    )
    print(f"\nTotal documents processed: {total_docs}")
    print(f"Total published: {total_published}")
    print("=== End Report ===\n")


async def run_reindex(settings: Settings) -> int:
    """Run the full re-index with store context.

    Args:
        settings: Configuration settings

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    corpus_root = Path(settings.corpus_root)
    backfill_dir = Path(settings.backfill_dir)

    logger.info(f"Starting re-index: corpus={corpus_root}, backfill={backfill_dir}")

    corpus_report = None
    backfill_count = 0

    try:
        # Enter store context
        async with async_store_context(settings):
            logger.info("Store context established")

            # Reindex deterministic corpus (TASK-RIP-005)
            logger.info("Re-indexing deterministic corpus...")
            corpus_report = await reindex_corpus(corpus_root, publish_episode)
            logger.info(
                f"Corpus re-index complete: {corpus_report.published_count} published"
            )

            # Process reviewed backfill (TASK-RIP-006)
            logger.info("Processing reviewed backfill...")
            backfill_count = await process_backfill(backfill_dir, publish_episode)
            logger.info(f"Backfill processing complete: {backfill_count} published")

            # Print report
            print_report(corpus_report, backfill_count)

            logger.info("Re-index completed successfully")
            return 0

    except Exception as e:
        logger.error(f"Re-index failed: {e}", exc_info=True)

        # Print partial report if we have it
        if corpus_report is not None:
            print("\n=== Partial Report (before failure) ===")
            print(f"Corpus published: {corpus_report.published_count}")
            print(f"Backfill published: {backfill_count}")
            print(f"Unparseable: {corpus_report.unparseable_count}")
            print(f"Unrecognized: {corpus_report.unrecognized_count}")

        print(
            f"\nERROR: Re-index failed: {e}\n"
            f"Documents that failed to publish will be retried on next run.",
            file=sys.stderr,
        )
        return 1


async def main() -> None:
    """Main entrypoint for re-index CLI."""
    parser = argparse.ArgumentParser(
        description="Re-index deterministic corpus and reviewed backfill"
    )
    parser.parse_args()  # Parse args for --help support

    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        print(f"ERROR: Failed to load settings: {e}", file=sys.stderr)
        sys.exit(1)

    # Run re-index
    exit_code = await run_reindex(settings)
    sys.exit(exit_code)


def sync_main() -> None:
    """Synchronous wrapper for async main."""
    asyncio.run(main())


if __name__ == "__main__":
    sync_main()
