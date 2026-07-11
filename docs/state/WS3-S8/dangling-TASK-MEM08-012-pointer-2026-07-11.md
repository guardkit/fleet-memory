# Dangling-reference pointer — TASK-MEM08-012

**Filed:** 2026-07-11 · WS3-S8 tracker sweep (fleet-memory) · pointer note only, no code change

## What the audit flags
`guardkit task audit` reports one `dangling_reference`: **TASK-MEM08-012**, referenced by
first-party source `src/fleet_memory/retrieval/core.py:96` (docstring of `_item_domain_tags`),
with no task file in `tasks/**` declaring that id.

## Adjudication
This is **not a real backlog task and needs no task file.** The id is used inside a docstring
as a *forward-looking marker*: the writer (`writer/core.py`) currently persists a record's
`domain_tags` only inside the embedded `content` JSON, not as a top-level stored field, so the
retrieval reader resolves tags top-level-first and falls back to parsing `content`. The
docstring notes this is "forward-compatible if the writer later lifts `domain_tags` to a
top-level field" and tags that hypothetical future work with the informal id `TASK-MEM08-012`.

- No lost/undeclared work product — the behaviour it describes is **already implemented** in
  `_item_domain_tags` (top-level-then-content resolution). The marker points at a *possible
  future writer change*, not an open obligation.
- The id is malformed relative to the repo convention (`MEM08` vs the `TASK-MEM-0nn` scheme),
  confirming it is an inline annotation, not a tracked backlog id.

## Disposition
**Reported, not resolved in the tracker.** The audit will continue to surface this dangling
reference until the docstring is edited — which is a **code change, out of scope for a
mechanical tracker sweep** (WS3-S8 rules: tracker/doc paths only). If the team wants the alarm
cleared, the one-line fix is to drop or reword the `(TASK-MEM08-012)` parenthetical in
`src/fleet_memory/retrieval/core.py:96`; that belongs to a code-touching session, not this sweep.
