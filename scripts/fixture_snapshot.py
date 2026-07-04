"""Fixture CLI entrypoint over the fleet_memory.fixture package (TASK-ABL5-005).

Operator/adapter-facing argparse wrapper — the build plan's named entrypoint.
All logic lives in the package; this script only parses arguments, resolves
the snapshot source DSN, dispatches, and prints machine-readable results:

    python scripts/fixture_snapshot.py snapshot        --fixture-id v1 [--source-dsn DSN]
    python scripts/fixture_snapshot.py verify          --fixture-id v1
    python scripts/fixture_snapshot.py restore         --fixture-id v1 --target-dsn DSN
    python scripts/fixture_snapshot.py cut             --target-dsn DSN --cut-date 2026-06-25
    python scripts/fixture_snapshot.py discard-scratch --target-dsn DSN --rollout-id run_01
    python scripts/fixture_snapshot.py list-scratch    --target-dsn DSN

DSN policy: ``snapshot`` falls back to the ``FLEET_MEMORY_PG_DSN`` environment
variable (the settings convention) so it runs on the GB10 without pasting
credentials into argv. ``--target-dsn`` is always explicit — restore/cut/
discard must never accidentally point at the live store via an ambient env
var. No DSN, password, or credential fragment ever reaches stdout/stderr:
success output is manifest/count JSON and errors carry only the package's
credential-free ``host:port/db`` labels.

Exit codes: 0 success; 1 fixture/tooling error (``FixtureError`` subclasses,
one credential-free line on stderr); 2 usage error (argparse / missing DSN).
Unexpected exceptions are not swallowed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from fleet_memory.fixture import (
    FixtureError,
    FixtureHashMismatchError,
    FixtureManifest,
    compute_content_hash,
    fixture_dir,
    read_manifest,
)
from fleet_memory.fixture.restore import restore_fixture
from fleet_memory.fixture.scratch import discard_scratch, list_scratch_projects
from fleet_memory.fixture.snapshot import create_snapshot
from fleet_memory.fixture.temporal_cut import apply_temporal_cut

DSN_ENV_VAR = "FLEET_MEMORY_PG_DSN"
DEFAULT_FIXTURES_ROOT = Path("eval") / "fixtures"

EXIT_OK = 0
EXIT_FIXTURE_ERROR = 1
EXIT_USAGE = 2


def _emit_json(payload: dict[str, object]) -> None:
    """Print ``payload`` as single-line JSON on stdout (machine-readable)."""
    print(json.dumps(payload, sort_keys=True))


def _manifest_payload(manifest: FixtureManifest) -> dict[str, object]:
    """Fixture id + content hash + row counts — never a DSN or credential."""
    return {
        "content_hash": manifest.content_hash,
        "fixture_id": manifest.fixture_id,
        "null_occurred_at_count": manifest.null_occurred_at_count,
        "table_row_counts": dict(manifest.table_row_counts),
    }


def _cmd_snapshot(args: argparse.Namespace) -> int:
    manifest = create_snapshot(args.source_dsn, args.fixture_id, args.fixtures_root)
    _emit_json(_manifest_payload(manifest))
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    fdir = fixture_dir(args.fixture_id, args.fixtures_root)
    manifest = read_manifest(fdir)
    actual = compute_content_hash(fdir)
    if actual != manifest.content_hash:
        # Message carries fixture id + expected/actual hashes; main() maps it
        # to exit 1 on stderr like every other FixtureError.
        raise FixtureHashMismatchError(args.fixture_id, manifest.content_hash, actual)
    print(f"fixture {args.fixture_id} OK sha256={actual}")
    return EXIT_OK


def _cmd_restore(args: argparse.Namespace) -> int:
    manifest = restore_fixture(args.fixture_id, args.target_dsn, args.fixtures_root)
    _emit_json(_manifest_payload(manifest))
    return EXIT_OK


def _cmd_cut(args: argparse.Namespace) -> int:
    result = apply_temporal_cut(args.target_dsn, args.cut_date, dry_run=args.dry_run)
    _emit_json(asdict(result))
    return EXIT_OK


def _cmd_discard_scratch(args: argparse.Namespace) -> int:
    deleted = discard_scratch(args.target_dsn, args.rollout_id)
    _emit_json({"deleted": deleted, "rollout_id": args.rollout_id})
    return EXIT_OK


def _cmd_list_scratch(args: argparse.Namespace) -> int:
    projects = list_scratch_projects(args.target_dsn)
    _emit_json({"scratch_projects": projects})
    return EXIT_OK


def _add_fixture_args(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--fixture-id", required=True, help="versioned fixture id (e.g. v1)")
    sub.add_argument(
        "--fixtures-root",
        type=Path,
        default=DEFAULT_FIXTURES_ROOT,
        help=f"fixtures directory (default: {DEFAULT_FIXTURES_ROOT})",
    )


def _add_target_dsn(sub: argparse.ArgumentParser) -> None:
    # Always explicit — never an env fallback (must not silently hit the live store).
    sub.add_argument("--target-dsn", required=True, help="per-run store DSN (explicit only)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture_snapshot",
        description="Ablation fixture tooling: snapshot/verify/restore, temporal cut, scratch.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="snapshot a store into a versioned fixture")
    _add_fixture_args(snapshot)
    snapshot.add_argument(
        "--source-dsn",
        default=None,
        help=f"source store DSN (default: ${DSN_ENV_VAR})",
    )
    snapshot.set_defaults(func=_cmd_snapshot)

    verify = sub.add_parser("verify", help="recompute a fixture's content hash")
    _add_fixture_args(verify)
    verify.set_defaults(func=_cmd_verify)

    restore = sub.add_parser("restore", help="restore a fixture into a fresh store")
    _add_fixture_args(restore)
    _add_target_dsn(restore)
    restore.set_defaults(func=_cmd_restore)

    cut = sub.add_parser("cut", help="apply the temporal cut on episode_meta.occurred_at")
    _add_target_dsn(cut)
    cut.add_argument("--cut-date", required=True, help="ISO date/datetime cut instant")
    cut.add_argument("--dry-run", action="store_true", help="preview counts without deleting")
    cut.set_defaults(func=_cmd_cut)

    discard = sub.add_parser("discard-scratch", help="delete a rollout's scratch project")
    _add_target_dsn(discard)
    discard.add_argument("--rollout-id", required=True, help="rollout id ([a-z0-9_]+)")
    discard.set_defaults(func=_cmd_discard_scratch)

    list_scratch = sub.add_parser("list-scratch", help="list scratch projects in a store")
    _add_target_dsn(list_scratch)
    list_scratch.set_defaults(func=_cmd_list_scratch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse handles usage errors (2) and --help (0)
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    if args.command == "snapshot" and not args.source_dsn:
        args.source_dsn = os.environ.get(DSN_ENV_VAR, "")
        if not args.source_dsn:
            print(
                f"error: snapshot needs a source DSN — pass --source-dsn or set ${DSN_ENV_VAR}",
                file=sys.stderr,
            )
            return EXIT_USAGE

    try:
        return args.func(args)
    except FixtureError as exc:
        # Package errors are credential-free by contract (sanitize_target/scrub_secrets).
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FIXTURE_ERROR


if __name__ == "__main__":
    sys.exit(main())
