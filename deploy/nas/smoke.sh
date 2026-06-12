#!/usr/bin/env bash
# Smoke tests for fleet_memory NAS Postgres deployment
# Gates G3-G5 from RUNBOOK-nas-postgres-deploy.md
# Exit non-zero on any gate failure

set -euo pipefail

# Load deployment configuration
if [ ! -f .env.deploy ]; then
    echo "ERROR: .env.deploy not found"
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

SSH="ssh -i $HOME/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes -p ${NAS_SSH_PORT} ${NAS_USER}@${NAS_HOST}"

echo "=== Smoke Tests for fleet_memory NAS Postgres ==="
echo ""

# GATE G3: pg_isready + pgvector extension
echo "=== GATE G3: Server Ready + pgvector Extension ==="
if $SSH "sudo -n /usr/local/bin/docker exec fleet_memory_postgres pg_isready -U fleet_memory" >/dev/null 2>&1; then
    echo "GATE G3.1 PASS: pg_isready accepts connections"
else
    echo "GATE G3.1 FAIL: pg_isready failed"
    exit 1
fi

VECTOR_CHECK=$($SSH "sudo -n /usr/local/bin/docker exec fleet_memory_postgres psql -U fleet_memory -d fleet_memory -t -c \"SELECT extname FROM pg_extension WHERE extname='vector';\"" | tr -d '[:space:]')

if [ "$VECTOR_CHECK" == "vector" ]; then
    echo "GATE G3.2 PASS: pgvector extension installed"
else
    echo "GATE G3.2 FAIL: pgvector extension not found"
    exit 1
fi

# GATE G4: Network path (LAN/Tailscale DSN, no SSH tunnel)
echo ""
echo "=== GATE G4: Network Path (LAN/Tailscale) ==="
if psql "postgresql://fleet_memory:${FLEET_MEMORY_PG_PASSWORD}@${NAS_HOST}:5432/fleet_memory" -c 'SELECT 1;' >/dev/null 2>&1; then
    echo "GATE G4 PASS: Direct network access successful"
else
    echo "GATE G4 FAIL: Cannot connect over network. Check DSM firewall rules."
    exit 1
fi

# GATE G5: Data on backed-up volume (not container-internal)
echo ""
echo "=== GATE G5: Data Persistence Location ==="
PG_VERSION=$($SSH "cat ${NAS_DOCKER_ROOT}/pgdata/PG_VERSION" 2>/dev/null | tr -d '[:space:]')

if [ "$PG_VERSION" == "16" ]; then
    echo "GATE G5 PASS: PG_VERSION=16 on ${NAS_DOCKER_ROOT}/pgdata (backed-up volume)"
else
    echo "GATE G5 FAIL: PG_VERSION not found or wrong version"
    echo "Expected: 16, Got: ${PG_VERSION:-<not found>}"
    echo "CRITICAL: Bind mount may be incorrect. DO NOT load data until fixed."
    exit 1
fi

echo ""
echo "=== All Gates Passed ==="
echo "G3: Server ready + pgvector installed"
echo "G4: Network access verified"
echo "G5: Data on backed-up volume"
echo ""
echo "Deployment is ready for use."
