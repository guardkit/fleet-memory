# RUNBOOK — NAS Postgres Deploy (fleet_memory durable store)

**Date:** 2026-06-12
**Status:** Ready to execute (Phase 0 manual once; Phases 1–4 scripted)
**Purpose:** Deploy Postgres 16 + pgvector to the Synology NAS as the durable fleet-memory store (FEAT-MEM-01, RD-4), fully automatable from the MacBook after one-time prep.
**Scope:** The DURABLE shared instance only. The ephemeral test instance (`deploy/local/`) is out of scope — it never touches the NAS.
**Related:** [phase-core-build-plan.md §FEAT-MEM-01](../research/ideas/phase-core-build-plan.md) — `deploy/nas/deploy.sh` is productized from the Phase 2/3 blocks below during the feature build.

---

## Credentials & secrets summary

| Item | Lives where | Notes |
|---|---|---|
| SSH **key** (`~/.ssh/fleet_memory_nas_ed25519`) | Mac keychain/agent | Auth to NAS. **Never** an SSH password in any file. |
| `deploy/nas/.env.deploy` | Mac only, `chmod 600`, gitignored (`.env*` already ignored) | `NAS_HOST`, `NAS_USER`, `NAS_SSH_PORT`, `NAS_DOCKER_ROOT`, `FLEET_MEMORY_PG_PASSWORD` |
| `.env` next to compose on NAS | NAS, `chmod 600`, rendered by deploy script | Only `POSTGRES_PASSWORD` (compose auto-loads it) |
| sudoers entry | NAS `/etc/sudoers.d/fleet_memory_deploy` | NOPASSWD for the docker binary only — not blanket sudo |

`deploy/nas/.env.deploy.example` (committed):

```bash
NAS_HOST=synology.local            # or Tailscale name/IP if the NAS runs the Tailscale package
NAS_USER=deploy_rich               # administrators-group user, key-auth only
NAS_SSH_PORT=22
NAS_DOCKER_ROOT=/volume1/docker/fleet_memory
FLEET_MEMORY_PG_PASSWORD=          # generate: openssl rand -base64 24
```

---

## Phase 0 — One-time NAS prep (manual, ~10 min, never repeated)

On DSM: **Control Panel → Terminal & SNMP → Enable SSH**. Confirm Container Manager is installed (Package Center). Then from the Mac:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/fleet_memory_nas_ed25519 -C "fleet-memory-deploy"
ssh-copy-id -i ~/.ssh/fleet_memory_nas_ed25519.pub -p 22 deploy_rich@synology.local
```

On the NAS (one interactive session, password prompts expected THIS TIME ONLY):

```bash
ssh -i ~/.ssh/fleet_memory_nas_ed25519 deploy_rich@synology.local

uname -m                                   # GATE G0a: must print x86_64
sudo -v                                    # prove admin
# Narrow NOPASSWD: docker binary only (argv[0] match covers `docker compose ...`)
echo "deploy_rich ALL=(ALL) NOPASSWD: /usr/local/bin/docker" | \
  sudo tee /etc/sudoers.d/fleet_memory_deploy
sudo chmod 440 /etc/sudoers.d/fleet_memory_deploy
mkdir -p /volume1/docker/fleet_memory/pgdata
exit
```

DSM firewall (Control Panel → Security → Firewall): allow TCP 5432 from the LAN subnet and, if the NAS is on the tailnet, `100.64.0.0/10`. Deny otherwise.

**GATE G0 (run from Mac — all three must pass before Phase 1):**

```bash
ssh -i ~/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes deploy_rich@synology.local \
  'echo SSH_OK && sudo -n /usr/local/bin/docker version --format "DOCKER_OK {{.Server.Version}}" && uname -m'
# PASS: prints SSH_OK, DOCKER_OK <version>, x86_64 — no password prompts anywhere.
# FAIL on prompt: sudoers entry wrong. FAIL on arch: STOP — image strategy changes.
```

## Phase 1 — Local env (Mac)

```bash
cd ~/Projects/appmilla_github/fleet-memory/deploy/nas
cp .env.deploy.example .env.deploy && chmod 600 .env.deploy
# fill values; generate the DB password:
openssl rand -base64 24
grep -c '=$' .env.deploy   # GATE G1 PASS: prints 0 (no empty values)
```

## Phase 2 — Deploy (idempotent; this becomes `deploy/nas/deploy.sh`)

```bash
set -euo pipefail
source .env.deploy
SSH="ssh -i $HOME/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes -p ${NAS_SSH_PORT} ${NAS_USER}@${NAS_HOST}"

# 2a. Sync compose folder (repo copy is canonical; NAS copy is an artifact)
rsync -avz -e "ssh -i $HOME/.ssh/fleet_memory_nas_ed25519 -p ${NAS_SSH_PORT}" \
  --exclude '.env.deploy*' docker-compose.yml ${NAS_USER}@${NAS_HOST}:${NAS_DOCKER_ROOT}/

# 2b. Render runtime .env on the NAS (DB password only), lock it down
$SSH "printf 'POSTGRES_PASSWORD=%s\n' '${FLEET_MEMORY_PG_PASSWORD}' > ${NAS_DOCKER_ROOT}/.env && chmod 600 ${NAS_DOCKER_ROOT}/.env"

# 2c. Up
$SSH "cd ${NAS_DOCKER_ROOT} && sudo -n /usr/local/bin/docker compose up -d"

# GATE G2 — container healthy
$SSH "sudo -n /usr/local/bin/docker ps --filter name=fleet_memory_postgres --format '{{.Status}}'"
# PASS: starts with "Up". FAIL: sudo -n docker logs fleet_memory_postgres, fix, re-run (idempotent).
```

## Phase 3 — Validation gates (from the Mac)

```bash
# GATE G3 — server ready + pgvector present
$SSH "sudo -n /usr/local/bin/docker exec fleet_memory_postgres pg_isready -U fleet_memory"
$SSH "sudo -n /usr/local/bin/docker exec fleet_memory_postgres psql -U fleet_memory -d fleet_memory \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;' -c \"SELECT extname, extversion FROM pg_extension WHERE extname='vector';\""
# PASS: accepting connections; one row e.g. vector | 0.8.x

# GATE G4 — network path the code will actually use (no SSH tunnel)
psql "postgresql://fleet_memory:${FLEET_MEMORY_PG_PASSWORD}@${NAS_HOST}:5432/fleet_memory" -c 'SELECT 1;'
# PASS: returns 1. FAIL: DSM firewall rule (Phase 0) or port mapping.

# GATE G5 — data lands on the backed-up volume, not container-internal
$SSH "ls ${NAS_DOCKER_ROOT}/pgdata/PG_VERSION && cat ${NAS_DOCKER_ROOT}/pgdata/PG_VERSION"
# PASS: prints 16. FAIL: bind mount wrong — STOP, do not load data.
```

**GATE G6 — reboot persistence (once, at a convenient moment):** reboot the NAS from DSM; after it returns, re-run G2+G4. PASS: container auto-restarted (`restart: unless-stopped` + Container Manager autostart) and accepts connections with data intact.

## Phase 4 — Ops

- **Backup:** confirm `/volume1/docker/fleet_memory` is inside an existing Hyper Backup / Snapshot Replication schedule. Consistent backups: snapshot is crash-consistent (fine for this corpus); belt-and-braces is a nightly `pg_dump` cron into the same share — defer until the store carries non-reindexable data (per ADR-SP-007 it currently never does).
- **Upgrade:** bump image tag in repo compose → re-run Phase 2 (idempotent). Postgres MAJOR upgrades need dump/restore — separate task, never casual.
- **Rollback:** `$SSH "cd ${NAS_DOCKER_ROOT} && sudo -n /usr/local/bin/docker compose down"` (NO `-v` — see below), restore `pgdata/` from snapshot if needed, `compose up -d`. Worst case for this store is always: drop, redeploy, re-index from markdown.

## Decision gates

| Gate | Test | PASS → | FAIL → |
|---|---|---|---|
| G0 | Batch SSH + `sudo -n docker` + x86_64 | Phase 1 | Fix key/sudoers; if ARM arch, stop and re-plan image |
| G1 | `.env.deploy` complete, mode 600 | Phase 2 | Fill values |
| G2 | Container Up | G3 | Read logs, fix, re-run |
| G3 | pg_isready + pgvector ext | G4 | Image/init issue |
| G4 | psql over LAN/Tailscale DSN | G5 | Firewall/port |
| G5 | `pgdata/PG_VERSION` on /volume1 path | Done (G6 when convenient) | **STOP** — bind mount wrong |

## What NOT to do

- Do NOT put an SSH password in any `.env` (or use `sshpass`). Key auth + scoped NOPASSWD is the automation path.
- Do NOT widen the sudoers entry beyond the docker binary, and do NOT deploy as DSM `root`.
- Do NOT run `docker compose down -v` — `-v` deletes the pgdata volume mount contents' container-side bindings; rollback is snapshot-restore, never volume nuke.
- Do NOT expose 5432 beyond LAN + tailnet, and do NOT point any automated test gate at this instance (hermeticity AC in FEAT-MEM-01).
- Do NOT edit compose on the NAS directly — repo is canonical; change there, re-run Phase 2.
- Do NOT skip G5. A wrong bind mount fails silently until the first NAS update eats the data.

---

## Provisioning record & corrections — 2026-06-21 (executed on the GB10, target `whitestocks`)

As-built record of the first real provisioning, kept for rebuilds. It **diverges from Phase 0 above**, and Phase 0 was **missing two DSM prerequisites** that blocked the run — both captured below. On a rebuild, follow *this* checklist; Phase 0's snippets are the template it corrects.

**Divergences from the 2026-06-12 plan**

- **Host = the GB10 (`promaxgb10-41b1`), not the Mac.** The output-side loop runs Forge on the GB10, so the key + `.env.deploy` are provisioned on that box (the one that runs the deploy). Everything below was run on the GB10 unless it says *interactive NAS session*.
- **The key did not pre-exist** anywhere; it was generated fresh on the GB10 (the Mac had no `fleet_memory_nas_ed25519`).

**Worked values (non-secret)**

```bash
NAS_HOST=whitestocks.tailebf801.ts.net     # Tailscale MagicDNS name (IPv4 100.92.74.2)
NAS_USER=RichardWoollcott                  # DSM account NAME (not the email); must be in administrators
NAS_SSH_PORT=22
NAS_DOCKER_ROOT=/volume1/docker/fleet_memory
# FLEET_MEMORY_PG_PASSWORD: openssl rand -base64 24, lives ONLY in deploy/nas/.env.deploy (gitignored) — never committed
```

DSM had several near-identical accounts (`RichardWoollcott`, `richardwoollcotthotmail.com`, a deactivated `admin`). `RichardWoollcott` is the chosen deploy identity — use it consistently as `NAS_USER` so the account owning the container files is the one Forge connects as.

**Step 1 — generate the key (GB10)**

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/fleet_memory_nas_ed25519 -C fleet-memory-deploy@gb10 -N ''
ls -la ~/.ssh/fleet_memory_nas_ed25519*    # confirm BOTH the private key and .pub exist before continuing
```

`-N ''` = no passphrase (required for the scripts' unattended `BatchMode=yes`).

**Step 2 — DSM prerequisite #1: enable User Home  [GAP in Phase 0 — this blocked the run]**

DSM → Control Panel → User & Group → Advanced → tick *Enable user home service* → Apply. Without it the user has no `/var/services/homes/<user>`, so there is nowhere to write `~/.ssh/authorized_keys`. Symptom seen this run: `ssh-copy-id` authenticated, then failed with `Could not chdir to home directory ... No such file or directory` and `mkdir: cannot create directory '.ssh': Permission denied`.

**Step 3 — DSM prerequisite #2: user in administrators  [Phase 0 assumed it — verify explicitly]**

DSM → User & Group → User → click `RichardWoollcott` → ensure **administrators** is ticked. Synology SSH only accepts administrators-group accounts, and the deploy needs sudo.

**Step 4 — install the key on the NAS (run on the GB10; lands on whitestocks)**

```bash
ssh-copy-id -i ~/.ssh/fleet_memory_nas_ed25519.pub -p "$NAS_SSH_PORT" "$NAS_USER@$NAS_HOST"
# prompts for RichardWoollcott's DSM password ONCE (bootstrap); expect: Number of key(s) added: 1
```

**Step 5 — passwordless docker-sudo (interactive NAS session)**

Phase 0 names this drop-in `fleet_memory_deploy`; this run created `fleet_memory_docker` (functionally identical — note the filename so a rebuild does not make a duplicate).

```bash
ssh -p "$NAS_SSH_PORT" "$NAS_USER@$NAS_HOST"          # interactive; DSM password OK here
which docker                                          # CONFIRM the path — was /usr/local/bin/docker
echo 'RichardWoollcott ALL=(ALL) NOPASSWD: /usr/local/bin/docker' | sudo tee /etc/sudoers.d/fleet_memory_docker
sudo chmod 440 /etc/sudoers.d/fleet_memory_docker
sudo visudo -c -f /etc/sudoers.d/fleet_memory_docker  # must report: parsed OK
exit
```

The sudoers path must match `which docker` exactly; `deploy.sh`/`smoke.sh` hardcode `/usr/local/bin/docker`.

**Step 6 — .env.deploy (GB10)**

```bash
cd ~/Projects/appmilla_github/fleet-memory/deploy/nas
cp .env.deploy.example .env.deploy && chmod 600 .env.deploy
openssl rand -base64 24             # paste into FLEET_MEMORY_PG_PASSWORD
nano .env.deploy                    # fill the five values above
git check-ignore deploy/nas/.env.deploy            # PASS: echoes the path
grep -c '^FLEET_MEMORY_PG_PASSWORD=.\+' .env.deploy # PASS: prints 1 (populated) without revealing it
```

**Gate — verify before any deploy (GB10)**

```bash
ssh -i ~/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes -p "$NAS_SSH_PORT" "$NAS_USER@$NAS_HOST" 'echo OK'
# PASS: prints OK, no password prompt → key + reach good
ssh -i ~/.ssh/fleet_memory_nas_ed25519 -o BatchMode=yes -p "$NAS_SSH_PORT" "$NAS_USER@$NAS_HOST" 'sudo -n /usr/local/bin/docker ps'
# PASS: prints the container table (FalkorDB was already running) → key + admin group + passwordless docker-sudo all proven
# FAIL (sudo: a password is required) → Step 5 did not take, or DSM wiped it (see caveats)
```

Both gates green on this run. Provisioning complete — the actual stand-up is deliberately left to the output-loop executor running `deploy.sh`/`smoke.sh` as typed steps (NOT a manual `./deploy.sh`), so the executor itself is proven; see [output-loop-exemplar-build-plan.md §FORGE-OL-04](../research/ideas/output-loop-exemplar-build-plan.md).

**Forward caveats (most likely rebuild-breakers)**

- **DSM major upgrades can wipe `/etc/sudoers.d/`.** If a working deploy suddenly demands a sudo password, re-do Step 5 first.
- **Tailscale node-key expiry.** On 2026-06-21 `whitestocks` showed *Key expiry: in 1 month*; when it lapses the NAS drops off the tailnet and the deploy loses its route. Disable key expiry for the NAS in the Tailscale admin console (Machines → whitestocks → Disable key expiry) — it is fixed infrastructure.
- **Re-provisioning a different host** (e.g. the second Spark): repeat Steps 1, 4, 6 on that host; Steps 2/3/5 are NAS-side and already done. One key per host beats copying the private key.

*FEAT-MEM-01 productizes Phases 2–3 as `deploy/nas/deploy.sh` + `deploy/nas/smoke.sh` with these gates inline; this runbook remains the operator reference and the Phase 0 record.*
