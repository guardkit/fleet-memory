---
id: TASK-MEM-008
title: NAS deploy execution and smoke (operator)
status: backlog
created: 2026-06-12T17:00:00Z
updated: 2026-06-12T17:00:00Z
priority: high
task_type: operator_handoff
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 4
implementation_mode: direct
complexity: 1
estimated_minutes: 30
dependencies: [TASK-MEM-007]
tags: [nas, synology, operator, live-infrastructure]
test_results:
  status: pending
  coverage: null
  last_run: null
---

# Task: NAS deploy execution and smoke (operator)

## Description

Deploy the durable shared Postgres instance to the live Synology NAS using the
scripted path authored in TASK-MEM-007, and verify it with the documented smoke
gates. This is live-infrastructure, human-in-the-loop work: AutoBuild must never
reach the NAS (the hermeticity acceptance criterion depends on it), so this task
is `operator_handoff` by design — confirmed by the operator at plan time.

## Required operator follow-up

This task is `task_type: operator_handoff` — AutoBuild will not attempt it. The
operator must verify the runtime acceptance criteria below manually, then mark
the task complete via `/task-complete`.

- **AC-1**: Phase 0 one-time NAS prep done (SSH key, narrow-docker sudoers, DSM firewall LAN+tailnet rule) and Gate **G0** passes from the Mac (`uname -m` → x86_64; key-auth SSH; NOPASSWD docker)
- **AC-2**: `deploy/nas/deploy.sh` runs from the Mac and Gate **G2** passes (container `fleet_memory_postgres` is `Up` on the NAS)
- **AC-3**: `deploy/nas/smoke.sh` runs from the Mac and Gates **G3, G4, G5** all PASS — G3: `pg_isready` over SSH; G4: `psql` over the LAN/Tailscale DSN returns `1` (the same network path the service will use); G5: `${NAS_DOCKER_ROOT}/pgdata/PG_VERSION` reads `16` (data on the backed-up share)
- **AC-4**: Gate **G6** — after a DSM reboot, G2 and G4 re-pass without manual intervention (`restart: unless-stopped` proven)
- **AC-5**: Port 5432 is reachable from LAN/tailnet only; a connection attempt from outside is refused (DSM firewall rule verified)

## BDD Scenarios Covered

- "The documented smoke check verifies the shared instance end-to-end"
- "Memories on the durable shared instance survive a restart"
- "The durable shared instance refuses connections from outside the private network"

## Implementation Notes

- Runbook: docs/runbooks/RUNBOOK-nas-postgres-deploy.md (Phases 0–4, gates G0–G6)
- Estimated operator wall-clock: 30–45 min including the one-time Phase 0
- Credentials: `deploy/nas/.env.deploy` (Mac-only, chmod 600, gitignored); generate `FLEET_MEMORY_PG_PASSWORD` via `openssl rand -base64 24`
- After completion, the `mac-dev` profile (`.env`) can point `FLEET_MEMORY_PG_DSN` at the NAS for development reads/writes
