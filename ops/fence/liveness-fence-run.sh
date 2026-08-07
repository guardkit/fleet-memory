#!/usr/bin/env bash
# Liveness-fence run wrapper (memory ladder ⑦). One invocation == one check pass.
#
# Two questions per pass: how old is the newest thing memory learned, and did the
# relay go quiet while builds were finishing. Exit 0 means alive, 1 means alarm.
#
# Env: FLEET_MEMORY_PG_DSN et al arrive from the systemd unit's sops exec-env wrap —
# never from this file, never on argv (the CLI has no --dsn flag by policy).
set -euo pipefail

REPO=/home/richardwoollcott/Projects/appmilla_github/fleet-memory
STATE_DIR=/home/richardwoollcott/.local/state/fleet-memory

mkdir -p "$STATE_DIR"

cd "$REPO"
exec uv run --no-sync python -m fleet_memory.fence
