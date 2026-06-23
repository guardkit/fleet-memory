#!/usr/bin/env bash
# Deploy fleet_memory Postgres to Synology NAS
# Productized from RUNBOOK-nas-postgres-deploy.md Phases 2-3
# Idempotent: safe to re-run

set -euo pipefail

# Load deployment configuration
if [ ! -f .env.deploy ]; then
    echo "ERROR: .env.deploy not found. Copy from .env.deploy.example and fill values."
    exit 1
fi

source .env.deploy

# Validate required variables
for var in NAS_HOST NAS_USER NAS_SSH_PORT NAS_DOCKER_ROOT FLEET_MEMORY_PG_PASSWORD; do
    if [ -z "${!var}" ]; then
        echo "ERROR: ${var} not set in .env.deploy"
        exit 1
    fi
done

# SSH command template (key-based auth, no password)
SSH="ssh -i $HOME/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes -p ${NAS_SSH_PORT} ${NAS_USER}@${NAS_HOST}"

echo "=== Phase 2: Deploy fleet_memory Postgres to NAS ==="

# 2a. Sync compose folder (repo is canonical; NAS copy is an artifact)
echo "Syncing docker-compose.yml to NAS..."
# NB: "initdb" has NO trailing slash on purpose — rsync must copy the directory
# itself (-> ${NAS_DOCKER_ROOT}/initdb/) so the compose "./initdb" bind mount
# resolves. A trailing slash ("initdb/") copies only the *contents* into the
# docker root, leaving no initdb dir and failing the mount on Synology.
rsync -avz -e "ssh -i $HOME/.ssh/fleet_memory_nas_ed25519 -p ${NAS_SSH_PORT}" \
    --exclude '.env.deploy*' \
    docker-compose.yml initdb \
    ${NAS_USER}@${NAS_HOST}:${NAS_DOCKER_ROOT}/

# 2b. Render runtime .env on the NAS (DB password only), lock it down
echo "Rendering .env on NAS..."
$SSH "printf 'POSTGRES_PASSWORD=%s\n' '${FLEET_MEMORY_PG_PASSWORD}' > ${NAS_DOCKER_ROOT}/.env && chmod 600 ${NAS_DOCKER_ROOT}/.env"

# 2b-bis. Create the pgdata bind-mount target. Synology's docker does NOT
# auto-create bind-mount source directories (unlike upstream docker), so the
# compose volume mount fails with "Bind mount failed: ... does not exists"
# unless the directory already exists.
echo "Ensuring pgdata directory exists on NAS..."
$SSH "mkdir -p ${NAS_DOCKER_ROOT}/pgdata"

# 2c. Start container
echo "Starting container..."
$SSH "cd ${NAS_DOCKER_ROOT} && sudo -n /usr/local/bin/docker compose up -d"

echo ""
echo "=== GATE G2: Container Health Check ==="
CONTAINER_STATUS=$($SSH "sudo -n /usr/local/bin/docker ps --filter name=fleet_memory_postgres --format '{{.Status}}'")

if [[ "$CONTAINER_STATUS" == Up* ]]; then
    echo "GATE G2 PASS: Container is running"
    echo "Status: $CONTAINER_STATUS"
else
    echo "GATE G2 FAIL: Container not healthy"
    echo "Status: $CONTAINER_STATUS"
    echo ""
    echo "View logs with:"
    echo "  ssh -i ~/.ssh/fleet_memory_nas_ed25519 -p ${NAS_SSH_PORT} ${NAS_USER}@${NAS_HOST} sudo -n /usr/local/bin/docker logs fleet_memory_postgres"
    exit 1
fi

echo ""
echo "=== Deploy Complete ==="
echo "Run ./smoke.sh to validate gates G3-G5"
