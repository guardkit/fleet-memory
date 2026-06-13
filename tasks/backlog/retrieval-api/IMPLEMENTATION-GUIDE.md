# Implementation Guide — FEAT-MEM-05 Retrieval API + Context Assembly

Feature complexity: **7/10** · 7 tasks · 5 waves · execution: auto-detected.

This is the read half of the store contract that FEAT-MEM-03 wrote into. The
design is a layered service: validate → search → assemble → compose, with a
probe-set harness driving the acceptance gate. Each correctness property
(supersession default, budget boundary, injection rejection, parity size) is
isolated to a single task with its own Coach gate.

---

## Data Flow: Read/Write Paths

What to look for: every write path that produced the corpus, and every read
path this feature adds. The write side already exists (FEAT-MEM-03); this
feature builds the read side. There are **no disconnected read/write paths** —
every read terminates at a real consumer (search result / parity report).

```mermaid
flowchart LR
    subgraph Writes["Write Paths (existing — FEAT-MEM-03)"]
        W1["Deterministic Writer\nupsert + supersession"]
        W2["embed-on-write\n(store index config)"]
    end

    subgraph Storage["Storage (existing — FEAT-MEM-01)"]
        S1[("AsyncPostgresStore\n(fleet_memory, project, payload_type)")]
        S2[("pgvector index\n(768-dim cosine)")]
    end

    subgraph Reads["Read Paths (this feature)"]
        R1["search() entry\n(SearchRequest)"]
        R2["vector search core\n(filter + rank + supersession)"]
        R3["budgeted assembly\n(tiktoken) + coverage"]
        R4["job-band composition"]
        R5["probe-set harness\n→ parity report"]
    end

    W1 -->|"records + supersedes links"| S1
    W2 -->|"content vectors"| S2

    R1 -->|"validated request"| R2
    S1 -->|"typed records"| R2
    S2 -->|"cosine ranking"| R2
    R2 -->|"ranked results"| R3
    R3 -->|"assembled block + coverage"| R4
    R4 -->|"composed block"| R1
    R3 -->|"assembled results"| R5

    style R1 fill:#cfc,stroke:#090
    style R5 fill:#cfc,stroke:#090
```

_Caption: solid arrows = wired paths. The read side (R1–R5) is fully connected
to storage and terminates at the `search()` caller and the parity report._

**Disconnection Alert:** none. Every read path has a caller — `search()` is
invoked by FEAT-MEM-06 (MCP) / FEAT-MEM-08 (cutover); the harness is invoked by
the AC-3 gate and re-used by FEAT-MEM-07.

---

## Integration Contracts (sequence)

What to look for: the "fetch then discard" anti-pattern — data retrieved but
not passed onward. Here every retrieved result is threaded through assembly and
returned; nothing is fetched and dropped.

```mermaid
sequenceDiagram
    participant C as Caller
    participant V as SearchRequest (RA-001)
    participant Q as Search core (RA-002)
    participant E as Store + embed
    participant A as Assembly (RA-003)
    participant K as Composition (RA-004)

    C->>V: search(project, types, tags, query, budget, include_superseded)
    V->>V: validate (reject hyphen / unknown type / bad tag / neg budget / empty)
    V->>Q: validated SearchRequest
    Q->>E: embed(query) + filtered cosine query
    E-->>Q: typed records + scores
    Q->>Q: exclude superseded (unless flag) + deterministic tie-break
    Q->>A: ranked results (most-relevant-first)
    A->>A: tiktoken-measure, drop tail to fit budget
    A->>K: assembled block + coverage
    K->>K: tune type mix by complexity band (within budget)
    K-->>C: composed context block + coverage score
    Note over Q,A: ranked results are passed onward, never fetched-and-dropped
```

_Caption: the request is validated once (RA-001) and never re-validated
downstream; ranked results flow through assembly to the caller._

---

## Task Dependencies

What to look for: the parallel-safe pairs (green). Waves 4 and 5 each run two
independent tasks.

```mermaid
graph TD
    T1[RA-001: SearchRequest + validation] --> T2[RA-002: vector search core]
    T2 --> T3[RA-003: budgeted assembly + coverage]
    T3 --> T4[RA-004: job-band composition]
    T3 --> T5[RA-005: probe-set harness]
    T4 --> T6[RA-006: unit/security/concurrency tests]
    T5 --> T6
    T4 --> T7[RA-007: integration tests]
    T5 --> T7

    style T4 fill:#cfc,stroke:#090
    style T5 fill:#cfc,stroke:#090
    style T6 fill:#cfc,stroke:#090
    style T7 fill:#cfc,stroke:#090
```

_Tasks with green background can run in parallel within their wave._

### Execution waves

- **Wave 1:** RA-001
- **Wave 2:** RA-002
- **Wave 3:** RA-003
- **Wave 4:** RA-004 ‖ RA-005
- **Wave 5:** RA-006 ‖ RA-007

---

## §4: Integration Contracts

Cross-task data dependencies exist (model → search → assembly → composition /
harness), so each boundary is specified below. The seam-test stubs in the
consumer task files assert these.

### Contract: SearchRequest
- **Producer task:** TASK-RA-001
- **Consumer task(s):** TASK-RA-002
- **Artifact type:** in-process Pydantic v2 model
- **Format constraint:** Fully validated before it reaches search core — project
  is underscore-only, payload types are registry-known, domain tags are
  exact-match clean, budget ≥ 0, at least one of query/filter present. Search
  core executes; it must NOT re-validate.
- **Validation method:** Coach verifies `tests/unit/test_search_core.py` passes
  a pre-validated `SearchRequest` and search core raises no validation errors.

### Contract: RankedResults
- **Producer task:** TASK-RA-002
- **Consumer task(s):** TASK-RA-003
- **Artifact type:** in-process ordered list of ranked, supersession-resolved
  memories with relevance scores
- **Format constraint:** Ordered most-relevant-first; superseded records already
  excluded (or marked, when `include_superseded`); ties broken deterministically.
  Assembly drops from the tail to fit the budget.
- **Validation method:** Coach verifies the assembly boundary tests
  (2100→drop-lowest) rely on the list order, not re-ranking.

### Contract: AssembledContext
- **Producer task:** TASK-RA-003
- **Consumer task(s):** TASK-RA-004, TASK-RA-005
- **Artifact type:** in-process result object — assembled block string +
  coverage score (fraction filled + contributing payload types)
- **Format constraint:** Block measured with tiktoken `cl100k_base`; never
  exceeds `token_budget`; coverage fraction in 0.0–1.0 (0.0 at zero budget).
  Composition tunes the input mix but must not breach the budget; the harness
  compares the assembled result to a recorded baseline.
- **Validation method:** Coach verifies composition tests assert both
  band-difference AND within-budget, and harness tests compare against baselines.

### Contract: embed/store interface (existing infra boundary)
- **Producer:** FEAT-MEM-01 store (`AsyncPostgresStore` via `async_store_context`)
  + embed at llama-swap `:9000`
- **Consumer task(s):** TASK-RA-002
- **Artifact type:** pgvector cosine search over namespace
  `("fleet_memory", project, payload_type)`; embed → 768-dim vector
- **Format constraint:** Query embedded via the store index config / embed_fn
  (nomic-embed-text-v1.5, 768 dims, cosine); failures surface credential-free
  messages (mirror the `async_store_context` TimeoutError pattern).
- **Validation method:** Coach verifies the degradation tests (embed
  unavailable, store unreachable) raise clear, credential-free errors.

---

## Notes on open assumptions

- **ASSUM-001 (bands, low conf):** RA-004 must verify the band→mix mapping
  against guardkit's real job-specific builder before FEAT-MEM-08; record the
  verified mapping in `retrieval-api_assumptions.yaml`.
- **ASSUM-007 (parity tolerance, low conf):** RA-005 keeps `PARITY_TOLERANCE`
  (default 0) and `MIN_PROBE_SET_SIZE` (15) as named constants so OD-2's freeze
  decision is a one-line change.
- **ASSUM-008 / ASSUM-009:** implemented per the spec (reject empty request;
  omit oversized memory whole); both remain flagged for human confirmation.
