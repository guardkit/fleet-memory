#!/usr/bin/env bash
# Alert hook for the liveness fence (memory ladder ⑦).
#
# Deliberately NOT `set -e`. An alert that crashloops is worse than no alert, so this
# script always writes its loud line first and always exits 0, whatever else fails.
# Journal-only by design: no email, no Slack, no credential.

STATE_DIR=/home/richardwoollcott/.local/state/fleet-memory
STATUS_FILE="$STATE_DIR/liveness-fence-status.json"
LOG_FILE="$STATE_DIR/liveness-fence.log"

echo "MEMORY LIVENESS FENCE TRIPPED — the memory flywheel may be dark."
echo "  What the fence found: $STATUS_FILE"
echo "  History of lapses:    $LOG_FILE"
echo "  Read the last run:    journalctl --user -u fleet-memory-liveness-fence.service -n 30"

# Best-effort echo of the plain-language lines, so the journal alone is enough.
if [ -r "$LOG_FILE" ]; then
    tail -n 12 "$LOG_FILE" 2>/dev/null || true
fi

exit 0
