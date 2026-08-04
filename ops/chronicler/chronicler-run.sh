#!/usr/bin/env bash
# Chronicler scheduled-run wrapper (WS4-S7; scheduled 2026-08-04, the memory
# lane's follow-up). One invocation == one harvest pass over the durable store.
#
# Watermark: each successful run records its own START time; the next run
# passes it as --since so a pass only chronicles the new window (the first
# full-history pass of 2026-08-04 flooded 1,090 cards — bounded ever since).
# On failure the watermark is NOT advanced, so the missed window is re-covered
# by the next run (JetStream-style at-least-once; story cards are idempotent
# by filename, dataset rows carry run-stamped filenames for the intake side).
#
# Env: FLEET_MEMORY_PG_DSN et al arrive from the systemd unit's sops exec-env
# wrap — never from this file, never on argv (the CLI's own DSN policy).
set -euo pipefail

REPO=/home/richardwoollcott/Projects/appmilla_github/fleet-memory
OUT=/home/richardwoollcott/fleet-memory-out/chronicler
STATE_DIR=/home/richardwoollcott/.local/state/fleet-memory
WATERMARK="$STATE_DIR/chronicler.since"

mkdir -p "$OUT/dataset_intake" "$OUT/story_card_queue" "$STATE_DIR"

START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SINCE_ARGS=()
if [[ -s "$WATERMARK" ]]; then
    SINCE_ARGS=(--since "$(cat "$WATERMARK")")
fi

cd "$REPO"
uv run --no-sync python scripts/chronicler_harvest.py \
    --intake-dir "$OUT/dataset_intake" \
    --queue-dir "$OUT/story_card_queue" \
    "${SINCE_ARGS[@]}"

printf '%s\n' "$START" > "$WATERMARK"
