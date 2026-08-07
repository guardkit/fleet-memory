"""The liveness fence, as a command: ``python -m fleet_memory.fence``.

    python -m fleet_memory.fence [--json] [--store-only|--relay-only] ...

Exit codes:

    0   memory looks alive (or every tripped check is validly acknowledged)
    1   ALARM — one or more checks tripped, including "the fence cannot see"
    2   usage or configuration error, always naming what is missing
    20  unexpected internal error

The unit that runs this does **not** mask exit 1. A tripped fence must show up in
``systemctl --user --failed`` — that failed-unit list, plus the ``OnFailure=`` alert,
*is* the visibility channel. Masking it would rebuild the fail-open habit that let
memory go dark for a month.

**DSN policy: there is no ``--dsn`` flag, deliberately.** The DSN arrives only as
``FLEET_MEMORY_PG_DSN``, injected by the unit's ``sops exec-env`` wrap. Nothing here
prints an environment value, and every error string is scrubbed before it is shown.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from fleet_memory.fence import Status
from fleet_memory.fence.ack import ACK_FILENAME, read_ack
from fleet_memory.fence.builds import scan_builds
from fleet_memory.fence.check import FenceFacts, Thresholds, evaluate
from fleet_memory.fence.marker import read_marker
from fleet_memory.fence.report import append_alarm_log, write_status
from fleet_memory.fence.store_age import read_store_facts
from fleet_memory.settings import Settings

__all__ = ["build_arg_parser", "main"]

DSN_ENV_VAR = "FLEET_MEMORY_PG_DSN"
EMBED_ENV_VAR = "FLEET_MEMORY_EMBED_URL"

EXIT_OK = 0
EXIT_ALARM = 1
EXIT_USAGE = 2
EXIT_INTERNAL = 20

# Settings requires embed_url, but the fence never embeds anything. Same workaround
# (and same reason) as the Chronicler's harvest CLI: supply a placeholder rather than
# weaken the validator for everyone.
_PLACEHOLDER_EMBED_URL = "http://unused-by-fence"
# Only ever used when --relay-only means the store is not consulted at all.
_PLACEHOLDER_DSN = "postgresql://unused-by-relay-only-fence"


class _UsageError(Exception):
    """A named configuration problem: exit 2, never a guess."""


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Note the deliberate absence of a --dsn flag."""
    parser = argparse.ArgumentParser(
        prog="fleet_memory.fence",
        description=(
            "Check that the memory flywheel is still turning: how old the newest "
            "thing memory learned is, and whether the relay went quiet while builds "
            "were finishing."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one line of JSON instead of the plain-language report.",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--store-only", action="store_true", help="Only check how fresh the store is."
    )
    scope.add_argument(
        "--relay-only",
        action="store_true",
        help="Only check relay silence (no database connection is made).",
    )
    parser.add_argument("--store-max-age-hours", type=int, default=None, help="Override the limit.")
    parser.add_argument(
        "--build-window-hours", type=int, default=None, help="Override the build window."
    )
    parser.add_argument(
        "--min-builds", type=int, default=None, help="Override how many builds make a pattern."
    )
    parser.add_argument("--builds-dir", default=None, help="Override the build receipts directory.")
    parser.add_argument("--marker", default=None, help="Override the relay progress marker path.")
    parser.add_argument("--state-dir", default=None, help="Override the fence state directory.")
    parser.add_argument(
        "--watch-projects",
        default=None,
        help="Comma-separated projects to check individually (empty string for none).",
    )
    return parser


def _resolve_settings(args: argparse.Namespace) -> Settings:
    """Build Settings for this run. Names missing configuration; never guesses it."""
    overrides: dict[str, object] = {}
    dsn = os.environ.get(DSN_ENV_VAR)
    if args.relay_only:
        overrides["pg_dsn"] = dsn or _PLACEHOLDER_DSN
    elif not dsn:
        raise _UsageError(
            f"{DSN_ENV_VAR} is not set, so the fence cannot look at the memory store. "
            "The unit supplies it through its sops exec-env wrap; there is no --dsn "
            "flag by policy. Use --relay-only to skip the store check."
        )
    else:
        overrides["pg_dsn"] = dsn
    if EMBED_ENV_VAR not in os.environ:
        overrides["embed_url"] = _PLACEHOLDER_EMBED_URL
    if args.builds_dir is not None:
        overrides["fence_builds_dir"] = args.builds_dir
    if args.marker is not None:
        overrides["fence_relay_marker_path"] = args.marker
    if args.state_dir is not None:
        overrides["fence_state_dir"] = args.state_dir
    if args.watch_projects is not None:
        overrides["fence_watch_projects"] = args.watch_projects
    if args.store_max_age_hours is not None:
        overrides["fence_store_max_age_hours"] = args.store_max_age_hours
    if args.build_window_hours is not None:
        overrides["fence_build_window_hours"] = args.build_window_hours
    if args.min_builds is not None:
        overrides["fence_min_builds_in_window"] = args.min_builds
    try:
        return Settings(**overrides)
    except Exception as exc:
        raise _UsageError(f"the fence's configuration is not usable: {type(exc).__name__}") from exc


def _watch_projects(settings: Settings) -> tuple[str, ...]:
    raw = settings.fence_watch_projects or ""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def main(argv: list[str] | None = None, *, now: datetime | None = None, connection_factory=None):
    """Run one fence pass and return the process exit code."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    moment = now or datetime.now(UTC)

    try:
        settings = _resolve_settings(args)
    except _UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        projects = _watch_projects(settings)
        thresholds = Thresholds(
            store_max_age_hours=settings.fence_store_max_age_hours,
            build_window_hours=settings.fence_build_window_hours,
            min_builds_in_window=settings.fence_min_builds_in_window,
            relay_restart_grace_minutes=settings.fence_relay_restart_grace_minutes,
            watch_projects=projects,
        )
        state_dir = Path(settings.fence_state_dir).expanduser()

        store_facts = None
        if not args.relay_only:
            store_facts = read_store_facts(
                settings.pg_dsn, projects, connection_factory=connection_factory
            )

        builds = marker = None
        if not args.store_only:
            builds = scan_builds(settings.fence_builds_dir)
            marker = read_marker(settings.fence_relay_marker_path)

        ack = read_ack(state_dir / ACK_FILENAME, today=moment.date())
        facts = FenceFacts(store=store_facts, builds=builds, marker=marker, ack=ack)
        report = evaluate(
            facts,
            thresholds,
            moment,
            store_only=args.store_only,
            relay_only=args.relay_only,
        )

        if args.json:
            print(json.dumps(report.as_dict(), sort_keys=True))
        else:
            for line in report.lines():
                print(line)

        try:
            write_status(state_dir, report)
            append_alarm_log(state_dir, report, now=moment)
        except OSError as exc:
            print(
                "WARNING: the fence could not write its own record to "
                f"{state_dir} ({type(exc).__name__}); the verdict above still stands.",
                file=sys.stderr,
            )

        return EXIT_ALARM if report.status is Status.ALARM else EXIT_OK
    except Exception as exc:  # last resort: never die silently, never leak a secret
        from fleet_memory.fixture.dsn import scrub_secrets

        detail = scrub_secrets(str(exc), settings.pg_dsn)
        print(
            f"ERROR: the fence hit an unexpected problem ({type(exc).__name__}): {detail}",
            file=sys.stderr,
        )
        return EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
