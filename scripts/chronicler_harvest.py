"""Chronicler batch-harvester CLI entrypoint (WS4-S7).

Operator/scheduler-facing argparse wrapper over ``fleet_memory.chronicler``. This is a
BATCH JOB meant to be invoked on a schedule (cron / systemd timer) — NOT a resident
service (WS4 §4.2: the relay's operational record argues against another resident
consumer). One invocation == one harvest pass.

    uv run python scripts/chronicler_harvest.py [--run-id ID] [--since ISO8601] \
        [--dsn DSN] [--intake-dir DIR] [--queue-dir DIR] [--public-projects a,b]

DSN policy: falls back to ``FLEET_MEMORY_PG_DSN`` (the settings convention) so it runs on
the GB10 without pasting credentials into argv. No DSN/credential fragment ever reaches
stdout/stderr: success output is a single-line count JSON; errors carry no DSN.

Outputs (DF-008 split):
  - flywheel-tagged dataset rows (JSONL, PRIVATE) → intake dir
  - draft story-card markdown (human review queue) → queue dir

Exit codes: 0 success; 1 runtime error; 2 usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from fleet_memory.chronicler.run import run_chronicler
from fleet_memory.settings import Settings
from fleet_memory.store import async_store_context

DSN_ENV_VAR = "FLEET_MEMORY_PG_DSN"

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE = 2


def _emit_json(payload: dict[str, object]) -> None:
    """Print ``payload`` as single-line JSON on stdout (machine-readable)."""
    print(json.dumps(payload, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chronicler_harvest",
        description="Run one Chronicler harvest pass over the durable memory store.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Identifier for this run (default: a UTC timestamp).",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="ISO-8601 occurred_at lower bound for incremental harvests.",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help=f"Postgres DSN (default: ${DSN_ENV_VAR}).",
    )
    parser.add_argument("--intake-dir", default=None, help="Override dataset intake dir.")
    parser.add_argument("--queue-dir", default=None, help="Override story-card queue dir.")
    parser.add_argument(
        "--public-projects",
        default=None,
        help="Comma-separated allowlist of non-confidential projects.",
    )
    parser.add_argument(
        "--require-acceptance",
        action="store_true",
        help="Exit non-zero unless ≥1 dataset row AND ≥1 story card were emitted "
        "(the WS4-S7 acceptance gate).",
    )
    return parser


def _default_run_id() -> str:
    """A UTC timestamp run id (only place a clock is read — the harvest itself is pure)."""
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _resolve_settings(args: argparse.Namespace) -> Settings:
    """Build Settings, applying CLI overrides. DSN falls back to the env var."""
    dsn = args.dsn or os.environ.get(DSN_ENV_VAR)
    if not dsn:
        raise SystemExit(
            f"usage: no DSN provided (pass --dsn or set ${DSN_ENV_VAR})"
        )
    overrides: dict[str, object] = {"pg_dsn": dsn}
    if args.intake_dir is not None:
        overrides["chronicler_dataset_intake_dir"] = args.intake_dir
    if args.queue_dir is not None:
        overrides["chronicler_story_card_queue_dir"] = args.queue_dir
    if args.public_projects is not None:
        overrides["chronicler_public_projects"] = args.public_projects
    # embed_url is required by Settings but the harvest reads the store without embedding;
    # fall back to the env or a placeholder so a read-only harvest run does not require it.
    if "FLEET_MEMORY_EMBED_URL" not in os.environ and "embed_url" not in overrides:
        overrides["embed_url"] = os.environ.get(
            "FLEET_MEMORY_EMBED_URL", "http://unused-by-harvest"
        )
    return Settings(**overrides)


async def _run(args: argparse.Namespace) -> int:
    settings = _resolve_settings(args)
    run_id = args.run_id or _default_run_id()

    # The harvest reads content back from the store; it does not embed, so a fake embed
    # callable keeps the store context from requiring a live embed service.
    from fleet_memory.embed import make_fake_embed

    embed_fn = make_fake_embed(dims=settings.embed_dims)
    async with async_store_context(settings, embed_fn=embed_fn) as store:
        result = await run_chronicler(store, settings, run_id=run_id, since=args.since)

    _emit_json(result.as_dict())
    if args.require_acceptance and not result.meets_acceptance():
        return EXIT_RUNTIME_ERROR
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except SystemExit as exc:  # usage errors from _resolve_settings
        if exc.code and isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return EXIT_USAGE
        return int(exc.code or EXIT_OK)


if __name__ == "__main__":
    sys.exit(main())
