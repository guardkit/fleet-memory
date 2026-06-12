---
complexity: 4
created: 2026-06-12 17:00:00+00:00
dependencies:
- TASK-MEM-004
estimated_minutes: 50
feature_id: FEAT-CA81
id: TASK-MEM-007
implementation_mode: task-work
parent_review: TASK-REV-CA81
priority: high
status: design_approved
tags:
- nas
- synology
- deployment
- runbook-productization
task_type: infrastructure
test_results:
  coverage: null
  last_run: null
  status: pending
title: NAS deploy files (compose, deploy.sh, smoke.sh)
updated: 2026-06-12 17:00:00+00:00
wave: 3
---

# Task: NAS deploy files (compose, deploy.sh, smoke.sh)

## Description

AUTHOR (do not execute against the NAS) the durable-instance deployment artifacts
in `deploy/nas/`, productized from `docs/runbooks/RUNBOOK-nas-postgres-deploy.md`
Phases 2–3 with gates G2–G5 inline. This task creates files and validates their
syntax locally; the actual deployment to the live Synology NAS is TASK-MEM-008
(operator handoff). Mirrors the `deploy/local/` conventions (same image, same
`initdb/` pattern) so there is ONE NAS-container convention.

## Acceptance Criteria

- [ ] `deploy/nas/docker-compose.yml` exists: image `pgvector/pgvector:pg16`, service `fleet_memory_postgres`, `restart: unless-stopped`, bind mount `${NAS_DOCKER_ROOT}/pgdata:/var/lib/postgresql/data`, port `5432:5432`, `env_file: .env` (compose auto-loads `POSTGRES_PASSWORD`), mounts `./initdb` to `/docker-entrypoint-initdb.d`; comments document the DSM firewall expectation (LAN + tailnet `100.64.0.0/10` only)
- [ ] `deploy/nas/initdb/01_extensions.sql` contains `CREATE EXTENSION IF NOT EXISTS vector;` (same content as deploy/local — runbook gate G3 baked into the container)
- [ ] `deploy/nas/deploy.sh` is executable, `set -euo pipefail`, sources `.env.deploy`, performs rsync + remote `.env` render + `docker compose up -d` exactly per runbook Phases 2–3, carries gate G2 inline with PASS/FAIL echo labels, contains no `sshpass` and no plaintext password literal
- [ ] `deploy/nas/smoke.sh` is executable, carries gates G3 (pg_isready over SSH), G4 (`psql` over the LAN/Tailscale DSN returns 1), G5 (`pgdata/PG_VERSION` reads 16 on the backed-up share) inline with PASS/FAIL labels, and exits non-zero on any gate failure
- [ ] `deploy/nas/.env.deploy.example` is committed with the five runbook fields (`NAS_HOST`, `NAS_USER`, `NAS_SSH_PORT`, `NAS_DOCKER_ROOT`, `FLEET_MEMORY_PG_PASSWORD`) empty-valued, with the `openssl rand -base64 24` generation comment; `.env.deploy` itself is covered by the existing `.env*` gitignore rule (verify)
- [ ] `bash -n deploy/nas/deploy.sh && bash -n deploy/nas/smoke.sh` exits 0 (syntax check; run shellcheck too if available)
- [ ] All modified files pass project-configured lint/format checks with zero errors

## Test Requirements

- [ ] Syntax-level only (`bash -n`, optional shellcheck) — NO network calls, NO SSH, NO NAS contact in this task or its Coach validation

## BDD Scenarios Covered

- "The documented smoke check verifies the shared instance end-to-end" (file authoring; execution in TASK-MEM-008)
- "Memories on the durable shared instance survive a restart" (`restart: unless-stopped` + bind-mount on backed-up share)
- "The durable shared instance refuses connections from outside the private network" (firewall documentation + compose comments)

## Implementation Notes

- Source of truth: RUNBOOK-nas-postgres-deploy.md — keep gate numbering (G2–G5) and PASS/FAIL output format identical to the runbook blocks so operator muscle memory transfers
- SSH invocation shape: `ssh -i ~/.ssh/fleet_memory_nas_ed25519 -p $NAS_SSH_PORT $NAS_USER@$NAS_HOST` with `sudo /usr/local/bin/docker` (the narrow NOPASSWD sudoers entry)
- Underscores in every Postgres identifier (database `fleet_memory`, user `fleet_memory`)
- Do NOT add these scripts to any automated test gate — they are operator tools