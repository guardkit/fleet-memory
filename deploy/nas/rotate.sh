#!/usr/bin/env bash
# Rotate the fleet_memory Postgres role password on the NAS — one command.
#
# WHY THIS EXISTS (2026-07-05, ABL-001 run-3 credential-leak remediation):
# deploy.sh alone CANNOT rotate. The postgres image consumes POSTGRES_PASSWORD
# only on FIRST initdb of an empty pgdata; the bind-mounted pgdata persists, so
# re-running deploy.sh with a new password updates every file while the
# database keeps accepting the OLD (compromised) password — and gate G2
# ("container Up") passes anyway. Rotation = ALTER ROLE inside the live
# database, THEN sync the files, THEN prove the property itself:
# new password authenticates over TCP, old password is refused.
#
# USAGE:
#   cd deploy/nas
#   $EDITOR .env.deploy        # set FLEET_MEMORY_PG_PASSWORD to the NEW value
#                              # (generate: openssl rand -base64 24)
#   ./rotate.sh                # prompts once for the OLD password (optional:
#                              # enter empty to skip the old-password-dead gate)
#
# AFTER THIS SCRIPT (consumers of the DSN — see the printed checklist):
#   relay on the GB10 (deploy/relay/.env.deploy + compose restart), any shell
#   profiles exporting FLEET_MEMORY_PG_DSN, guardkit memory status to verify.
#
# Secrets hygiene: passwords travel via stdin end-to-end (never ssh/docker
# argv, never echoed); charset-guarded so SQL single-quoting cannot break.

set -euo pipefail

if [ ! -f .env.deploy ]; then
    echo "ERROR: .env.deploy not found. Copy from .env.deploy.example and fill values."
    exit 1
fi

source .env.deploy

for var in NAS_HOST NAS_USER NAS_SSH_PORT NAS_DOCKER_ROOT FLEET_MEMORY_PG_PASSWORD; do
    if [ -z "${!var}" ]; then
        echo "ERROR: ${var} not set in .env.deploy"
        exit 1
    fi
done

NEW_PW="${FLEET_MEMORY_PG_PASSWORD}"

# Charset guard: the runbook generates passwords with `openssl rand -base64 24`.
# Restricting to the base64 alphabet keeps the SQL single-quote below safe by
# construction (no quotes/backslashes possible) — regenerate rather than widen.
if ! [[ "${NEW_PW}" =~ ^[A-Za-z0-9+/=]+$ ]]; then
    echo "ERROR: FLEET_MEMORY_PG_PASSWORD contains characters outside the base64"
    echo "       alphabet. Regenerate with: openssl rand -base64 24"
    exit 1
fi

# Optional old password — enables GATE R3 (old credential refused). Read
# silently; never appears in argv or history.
OLD_PW=""
if [ -t 0 ]; then
    read -r -s -p "OLD password (empty to skip the old-credential-dead gate): " OLD_PW
    echo ""
fi
if [ -n "${OLD_PW}" ] && ! [[ "${OLD_PW}" =~ ^[A-Za-z0-9+/=]+$ ]]; then
    echo "WARNING: old password has non-base64 characters; skipping GATE R3."
    OLD_PW=""
fi

SSH="ssh -i $HOME/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes -p ${NAS_SSH_PORT} ${NAS_USER}@${NAS_HOST}"
DOCKER="sudo -n /usr/local/bin/docker"

echo "=== Rotate fleet_memory Postgres role password ==="

# R0. Container must be up (rotation targets the LIVE role).
CONTAINER_STATUS=$($SSH "${DOCKER} ps --filter name=fleet_memory_postgres --format '{{.Status}}'")
if [[ "${CONTAINER_STATUS}" != Up* ]]; then
    echo "GATE R0 FAIL: fleet_memory_postgres not running (status: ${CONTAINER_STATUS:-none})"
    echo "Run ./deploy.sh first."
    exit 1
fi
echo "GATE R0 PASS: container is running"

# R1. ALTER ROLE inside the container via the trusted unix socket.
# SQL arrives on stdin (psql -f -): the password never touches ssh/docker argv.
echo "Rotating role password (ALTER ROLE via unix socket)..."
printf "ALTER ROLE fleet_memory PASSWORD '%s';\n" "${NEW_PW}" | \
    $SSH "${DOCKER} exec -i fleet_memory_postgres psql -q -v ON_ERROR_STOP=1 -U fleet_memory -d fleet_memory -f -"
echo "GATE R1 PASS: ALTER ROLE accepted"

# R2. New password must authenticate over TCP (the real client path — socket
# auth is 'trust', so only a TCP login proves the credential). The password is
# read from stdin INSIDE the container; nothing secret in any argv.
echo "Verifying NEW password authenticates over TCP..."
if printf '%s\n' "${NEW_PW}" | $SSH "${DOCKER} exec -i fleet_memory_postgres bash -c 'IFS= read -r PGPASSWORD; export PGPASSWORD; psql -h 127.0.0.1 -p 5432 -U fleet_memory -d fleet_memory -tAc \"SELECT 1\"'" | grep -q '^1$'; then
    echo "GATE R2 PASS: new password authenticates"
else
    echo "GATE R2 FAIL: new password rejected over TCP — database and .env.deploy now DISAGREE."
    echo "Do NOT proceed; investigate before touching any consumer."
    exit 1
fi

# R3. Old password must be REFUSED (the property that makes this a rotation).
if [ -n "${OLD_PW}" ]; then
    echo "Verifying OLD password is refused..."
    if printf '%s\n' "${OLD_PW}" | $SSH "${DOCKER} exec -i fleet_memory_postgres bash -c 'IFS= read -r PGPASSWORD; export PGPASSWORD; psql -h 127.0.0.1 -p 5432 -U fleet_memory -d fleet_memory -tAc \"SELECT 1\"'" 2>/dev/null | grep -q '^1$'; then
        echo "GATE R3 FAIL: the OLD password still authenticates — rotation did not take."
        exit 1
    fi
    echo "GATE R3 PASS: old credential is dead"
else
    echo "GATE R3 SKIPPED: no old password provided"
fi

# R4. Sync the rendered runtime .env on the NAS so future `docker compose up`
# recreations agree with the live role (same render as deploy.sh step 2b —
# harmless for the running container, load-bearing for the next recreation).
echo "Rendering .env on NAS..."
printf 'POSTGRES_PASSWORD=%s\n' "${NEW_PW}" | \
    $SSH "cat > ${NAS_DOCKER_ROOT}/.env && chmod 600 ${NAS_DOCKER_ROOT}/.env"
echo "GATE R4 PASS: NAS .env rendered + chmod 600"

echo ""
echo "=== Rotation complete on the NAS ==="
echo ""
echo "Remaining consumers (checklist — nothing below is automated here):"
echo "  1. Relay (GB10): edit fleet-memory/deploy/relay/.env.deploy"
echo "     (FLEET_MEMORY_PG_DSN with the new password), then:"
echo "       cd deploy/relay && docker compose up -d && docker compose logs -f"
echo "     Expect a clean FastStream start, no auth errors."
echo "  2. Any shell profiles / loop-launch snippets exporting FLEET_MEMORY_PG_DSN"
echo "     (GB10 + Mac). Agent loops get FIXTURE DSNs only (P4) — never this one."
echo "  3. Verify end-to-end: guardkit memory status   (from a tailnet machine)"
echo "  4. Run ./smoke.sh for gates G3-G5 against the rotated credential."
