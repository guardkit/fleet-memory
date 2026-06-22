#!/usr/bin/env bash
# Smoke tests for the LOCAL ephemeral fleet_memory instance.
#
# Local analogues of the NAS gates G3-G5 (see deploy/nas/smoke.sh). The script's
# exit code IS the verdict: non-zero on any gate failure. Mirrors the
# run_smoke_tests step contract; .env.deploy is sourced from cwd (ENV_FILE is not
# consulted), and the NAS is never touched.
#
# Host requirement: a `psql` client on PATH for GATE G4 (the network-path gate
# connects to the published port the way application code would, not via
# docker exec). Install via `brew install libpq` (then link psql) or postgresql.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env.deploy ]; then
    set -a
    # shellcheck disable=SC1091
    source .env.deploy
    set +a
fi
PGPORT="${PGPORT:-5432}"
PG_PASS="${POSTGRES_PASSWORD:-fleet_memory}"

echo "=== Smoke Tests for local fleet_memory Postgres ==="
echo ""

# GATE G3: server ready + pgvector extension present
echo "=== GATE G3: Server Ready + pgvector Extension ==="
if docker compose exec -T postgres pg_isready -U fleet_memory >/dev/null 2>&1; then
    echo "GATE G3.1 PASS: pg_isready accepts connections"
else
    echo "GATE G3.1 FAIL: pg_isready failed"
    exit 1
fi

VECTOR_CHECK=$(docker compose exec -T postgres psql -U fleet_memory -d fleet_memory -tAc \
    "SELECT extname FROM pg_extension WHERE extname='vector';" | tr -d '[:space:]')
if [ "$VECTOR_CHECK" == "vector" ]; then
    echo "GATE G3.2 PASS: pgvector extension installed"
else
    echo "GATE G3.2 FAIL: pgvector extension not found"
    exit 1
fi

# GATE G4: network path the code will actually use (published port, no docker exec)
echo ""
echo "=== GATE G4: Network Path (localhost:${PGPORT}) ==="
if psql "postgresql://fleet_memory:${PG_PASS}@localhost:${PGPORT}/fleet_memory" -c 'SELECT 1;' >/dev/null 2>&1; then
    echo "GATE G4 PASS: direct network access successful"
else
    echo "GATE G4 FAIL: cannot connect over the published port (is psql installed? is the port mapped?)"
    exit 1
fi

# GATE G5: data directory initialised (local analogue of the NAS backed-up volume)
echo ""
echo "=== GATE G5: Data Persistence Location ==="
PG_VERSION=$(docker compose exec -T postgres cat /var/lib/postgresql/data/PG_VERSION 2>/dev/null | tr -d '[:space:]')
if [ "$PG_VERSION" == "16" ]; then
    echo "GATE G5 PASS: PG_VERSION=16 (data directory initialised)"
else
    echo "GATE G5 FAIL: PG_VERSION not found or wrong version (got: ${PG_VERSION:-<not found>})"
    exit 1
fi

echo ""
echo "=== All local gates passed ==="
echo "G3: server ready + pgvector installed"
echo "G4: network access verified"
echo "G5: data directory initialised"
