#!/usr/bin/env bash
# PATH hardening (2026-08-15): after the 08-13 reboot the systemd user manager's
# environment no longer carried ~/.local/bin, so the bare `uv` below exited 127 —
# ELEVEN consecutive silent fence failures. The fence must never depend on the
# session's PATH mood: state it explicitly.
export PATH="$HOME/.local/bin:$PATH"
# Liveness-fence run wrapper (memory ladder ⑦). One invocation == one check pass.
#
# Two questions per pass: how old is the newest thing memory learned, and did the
# relay go quiet while builds were finishing. Exit 0 means alive, 1 means alarm.
#
# Env: FLEET_MEMORY_PG_DSN et al arrive from the systemd unit's sops exec-env wrap —
# never from this file, never on argv (the CLI has no --dsn flag by policy).
#
# The named-volume reader is deliberately opt-in. Set both of these after the relay
# marker moves off the host path:
#   FLEET_MEMORY_FENCE_RELAY_MARKER_VOLUME  Docker named volume containing the marker
#   FLEET_MEMORY_FENCE_TOOL_IMAGE_ID        cached immutable sha256:<64 hex> image ID
# The marker is read at relay-progress.json in the volume root. The volume is inspected
# before it is mounted, so a misspelling cannot make Docker create an empty volume.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
STATE_DIR=${XDG_STATE_HOME:-"$HOME/.local/state"}/fleet-memory
MARKER_VOLUME=${FLEET_MEMORY_FENCE_RELAY_MARKER_VOLUME:-}
TOOL_IMAGE_ID=${FLEET_MEMORY_FENCE_TOOL_IMAGE_ID:-}

mkdir -p "$STATE_DIR"

cd "$REPO"

if [[ -z "$MARKER_VOLUME" && -z "$TOOL_IMAGE_ID" ]]; then
    exec uv run --no-sync python -m fleet_memory.fence
fi

unknown() {
    printf 'UNKNOWN: cannot read the relay progress marker from its named volume: %s\n' "$1" >&2
    exit 1
}

[[ -n "$MARKER_VOLUME" && -n "$TOOL_IMAGE_ID" ]] || \
    unknown 'both named-volume environment variables must be set'
[[ "$MARKER_VOLUME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || \
    unknown 'the configured volume name is not a Docker named-volume name'
[[ "$TOOL_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || \
    unknown 'the configured tool image is not an immutable sha256 image ID'

# Inspect first: `docker run --mount type=volume` creates a missing named volume.
docker volume inspect "$MARKER_VOLUME" >/dev/null 2>&1 || \
    unknown 'the configured named volume does not exist'

resolved_image_id=$(docker image inspect --format '{{.Id}}' "$TOOL_IMAGE_ID" 2>/dev/null) || \
    unknown 'the configured tool image is not present locally (no pull is attempted)'
[[ "$resolved_image_id" == "$TOOL_IMAGE_ID" ]] || \
    unknown 'the configured tool image did not resolve to its declared image ID'

umask 077
marker_copy=$(mktemp "$STATE_DIR/.relay-progress.XXXXXX") || \
    unknown 'a protected temporary marker could not be created'
cleanup_marker() {
    rm -f -- "$marker_copy"
}
trap cleanup_marker EXIT

if ! docker run --rm --network none --read-only \
    --mount "type=volume,src=$MARKER_VOLUME,dst=/relay-state,readonly" \
    --entrypoint /bin/cat \
    "$TOOL_IMAGE_ID" /relay-state/relay-progress.json >"$marker_copy"; then
    unknown 'the marker is missing or unreadable'
fi

if uv run --no-sync python -m fleet_memory.fence --marker "$marker_copy"; then
    fence_status=0
else
    fence_status=$?
fi
exit "$fence_status"
