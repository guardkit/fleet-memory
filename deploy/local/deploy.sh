#!/usr/bin/env bash
# Local ephemeral fleet_memory Postgres + pgvector via docker compose.
#
# Mirrors deploy/nas/deploy.sh's STEP CONTRACT (the deploy_compose step type) but
# drives a LOCAL compose instead of SSH+rsync — this is the disposable target for
# the FORGE-OL-04 end-to-end runbook test (forge TASK-FMDR-004). The NAS is never
# touched.
#
# Idempotent: safe to re-run (docker compose up -d --wait reconciles in place).
# .env.deploy is sourced from THIS directory (cwd), matching how the runbook step
# binds env — the handler's ENV_FILE variable is not consulted by this script.
set -euo pipefail
cd "$(dirname "$0")"

# THIS FOLDER CHOOSES ITS OWN COMPOSE PROJECT AND FILE (16 October 2026). A
# COMPOSE_PROJECT_NAME, COMPOSE_FILE or any other COMPOSE_* setting exported in
# the calling shell would otherwise point these commands at a different
# project. Inherited ones are dropped here; .env.deploy may still name the
# project (COMPOSE_PROJECT_NAME), and without it the project is "local", the
# name this folder has always given it. Every call names both explicitly.
for name in $(compgen -e); do
    case "$name" in COMPOSE_*) unset "$name" ;; esac
done
compose() {
    docker compose --project-directory . --file docker-compose.yml \
        --project-name "${COMPOSE_PROJECT_NAME:-local}" "$@"
}

# Optional env file — kept for parity with the NAS target. The local compose
# hardcodes the non-secret dev creds, so values here are optional overrides
# (e.g. PGPORT). A missing .env.deploy is NOT an error for the local target.
if [ -f .env.deploy ]; then
    set -a
    # shellcheck disable=SC1091
    source .env.deploy
    set +a
fi

echo "=== Local deploy: fleet_memory Postgres (pgvector) ==="
echo "Bringing the ephemeral compose up..."

# GATE G2: --wait blocks until the healthcheck passes (or fails non-zero).
compose up -d --wait

echo ""
echo "=== GATE G2: Container Health Check ==="
echo "GATE G2 PASS: container reported healthy"
compose ps
echo ""
echo "=== Deploy Complete ==="
echo "Run ./smoke.sh to validate local gates G3-G5"
