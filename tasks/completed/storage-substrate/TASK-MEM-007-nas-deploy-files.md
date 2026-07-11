---
id: TASK-MEM-007
title: NAS deploy files (compose, deploy.sh, smoke.sh)
status: completed
closed_by: WS3-S8-sweep-2026-07-11
completion_evidence: "rollup FEAT-CA81 completed"
pre_sweep_status: in_review
created: 2026-06-12 17:00:00+00:00
updated: 2026-06-12 17:00:00+00:00
priority: high
task_type: infrastructure
parent_review: TASK-REV-CA81
feature_id: FEAT-CA81
wave: 3
implementation_mode: task-work
complexity: 4
estimated_minutes: 50
dependencies:
- TASK-MEM-004
tags:
- nas
- synology
- deployment
- runbook-productization
test_results:
  status: pending
  coverage: null
  last_run: null
autobuild_state:
  current_turn: 1
  max_turns: 5
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-CA81
  base_branch: main
  started_at: '2026-06-12T19:22:23.438985'
  last_updated: '2026-06-12T19:32:07.893526'
  turns:
  - turn: 1
    decision: approve
    feedback: null
    timestamp: '2026-06-12T19:22:23.438985'
    player_summary: 'Implementation via task-work delegation. Files planned: 0, Files
      actual: 0'
    player_success: true
    coach_success: true
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
