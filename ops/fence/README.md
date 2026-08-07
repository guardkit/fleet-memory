# The liveness fence — install runbook

**Status: authored, verified, NOT installed.** Everything in this directory was written
and checked with `systemd-analyze verify`. Copying the units and enabling the timer is
an attended step you do by hand, in the order below.

## What this is, in one minute

The memory flywheel once stopped working for a month and nothing said so. Every layer
was built to stay quiet when unsure, so silence looked exactly like health.

The fence is the cure. Every four hours it asks two questions:

1. **How old is the newest thing memory learned?** If the newest row in the store is
   older than seven days, that is an alarm.
2. **Did the relay go quiet while work was happening?** If three or more builds
   finished in the last three days and memory recorded nothing in that time, that is an
   alarm.

If either question comes back badly, the unit exits non-zero — so it shows up in
`systemctl --user --failed` — and one loud line lands in the journal naming a file that
explains what happened in plain English.

Run it by hand any time:

```bash
cd ~/Projects/appmilla_github/fleet-memory
~/.local/bin/sops exec-env ~/.config/fleet-secrets/fleet-memory-pg/leg-env.enc.env \
    'uv run --no-sync python -m fleet_memory.fence'
```

## Install, in order (the order matters)

**1. Merge the lane.** Nothing changes yet — the fence is inert until its timer exists.

**2. Rebuild and recreate the relay** (attended). This is what makes the relay start
writing its progress marker and mounts the state directory into the container. Use the
only supported start path:

```bash
cd ~/.config/fleet-secrets && \
  ~/.local/bin/sops exec-env fleet-memory-pg/relay-env-deploy.enc.env \
  'docker compose -f ~/Projects/appmilla_github/fleet-memory/deploy/relay/docker-compose.yml up -d --build'
docker compose logs -f     # expect: "FastStream app started successfully!"
```

*Why before the timer:* until the relay has been rebuilt there is no marker, and the
fence will correctly report that it cannot see the relay.

**3. Check the marker exists.**

```bash
cat ~/.local/state/fleet-memory/relay-progress.json
```

It should carry a `started_at`. The file will be **owned by root** — the relay image
runs as root. That is expected; the fence only reads it. Do not change the ownership.

**4. Confirm the box keeps user services running when you log out.**

```bash
loginctl show-user "$USER" -p Linger      # expect Linger=yes
```

Without lingering the timer will not fire while you are logged out, and the fence will
quietly not run — which would be the original disease all over again.

**5. Copy the units and enable the timer** (attended). Copy verbatim — no substitution;
per-box variance is handled inside the units:

```bash
cp ~/Projects/appmilla_github/fleet-memory/ops/fence/fleet-memory-liveness-fence.service \
   ~/Projects/appmilla_github/fleet-memory/ops/fence/fleet-memory-liveness-fence.timer \
   ~/Projects/appmilla_github/fleet-memory/ops/fence/fleet-memory-liveness-fence-alert.service \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now fleet-memory-liveness-fence.timer
```

Enable **the timer only**. The service is a one-shot and stays inert until triggered.

**6. Dry-run it once by hand and read the result.**

```bash
systemctl --user start fleet-memory-liveness-fence.service
journalctl --user -u fleet-memory-liveness-fence.service -n 30
```

## Expect it to alarm shortly after install — that is it working

At the time this was written, nothing had written to the store since the 2026-08-04
operator re-index, and the Chronicler had been failing its scheduled run since 08-05 on
a Postgres connection timeout that nothing surfaced. Those are exactly the conditions
the fence exists to make loud.

**Do not tune the thresholds to make it green.** Either resume the writes, or file a
dated acknowledgement (below) that names the reason and the date it expires.

## Acknowledging a known-tripped check (the pressure valve)

Write `~/.local/state/fleet-memory/liveness-fence.ack`:

```json
{"reason": "waiting on the capture-outcome wiring",
 "until": "2026-08-18",
 "checks": ["relay_idle"]}
```

While that is present and unexpired, the named check prints as `HELD`, is still
recorded in the status file, and does not fail the run. Rules that keep it honest:

- `until` is **required**, and may be at most **14 days** away. Missing, unparseable,
  or further out and the whole file is rejected — the output says `ack rejected: ...`
  and the alarm stands. There is no silent honouring and no silent ignoring.
- An expired ack prints `ack expired on <date>` before the alarm it no longer covers.
- `checks` names what is covered: `store_age`, `store_age:<project>`, `relay_idle`.

## The knobs, and why they are set where they are

| Setting | Default | Why |
|---|---|---|
| `FLEET_MEMORY_FENCE_STORE_MAX_AGE_HOURS` | 168 (7 days) | Tolerates a long weekend plus a bank holiday; still catches a dark week. Would have caught the 2026-07-02→08-03 blackout on day 7 instead of day 31. Once writing build outcomes is automatic rather than a human close ritual, this can tighten to 72h. |
| `FLEET_MEMORY_FENCE_BUILD_WINDOW_HOURS` | 72 (3 days) | Enough builds for silence to mean something. |
| `FLEET_MEMORY_FENCE_MIN_BUILDS_IN_WINDOW` | 3 | One build proves nothing; three across three days is a pattern. |
| `FLEET_MEMORY_FENCE_RELAY_RESTART_GRACE_MINUTES` | 75 | A container recreate orphans an in-flight delivery until `ack_wait` expires (~1 hour by record). 75 minutes covers it with slack. |
| `FLEET_MEMORY_FENCE_WATCH_PROJECTS` | `guardkit` | The whole store is always checked; these projects also get their own check. **`jarvis` is deliberately absent** — its writer is dark by record, so it would alarm truthfully but uselessly on every run. Add it once re-armed; that is the first addition. |
| `FLEET_MEMORY_FENCE_BUILDS_DIR` | `~/forge-state/receipts` | The fence reads only the folder names; no database, no lock. |
| `FLEET_MEMORY_FENCE_RELAY_MARKER_PATH` | `~/.local/state/fleet-memory/relay-progress.json` | Same state directory as the Chronicler's watermark. |

## Notes

- **No new secret.** The fence reuses the Chronicler's own env family
  (`fleet-memory-pg/leg-env.enc.env`), so there is no fleet-secrets register row to add
  and no `/connz` baseline diff to take — nothing touches the broker.
- **The fence never writes to the store.** Its database session sets
  `default_transaction_read_only = on` before it asks anything.
- **No DSN on the command line, by policy.** There is no `--dsn` flag. The DSN arrives
  only as `FLEET_MEMORY_PG_DSN` from the `sops exec-env` wrap, and no environment value
  ever appears in the output, the status file, or the log.
- **Alerts are journal-only in v1.** Email or Slack would need a new config path and a
  new credential; that is a later, separate, opt-in change.
- **Removing the fence** = `systemctl --user disable --now fleet-memory-liveness-fence.timer`.
  The relay's marker write is harmless on its own and can stay.

## Files

| File | What it is |
|---|---|
| `liveness-fence-run.sh` | The wrapper the unit runs. Env comes from the unit's sops wrap, never from here. |
| `fleet-memory-liveness-fence.service` | The one-shot check. Exit code is not masked. |
| `fleet-memory-liveness-fence.timer` | Four-hourly cadence. **This is the thing you enable.** |
| `fleet-memory-liveness-fence-alert.service` | Pulled in by `OnFailure=`. |
| `fence-alert.sh` | Always writes one loud journal line; always exits 0. |
