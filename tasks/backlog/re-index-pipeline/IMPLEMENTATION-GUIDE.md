# Implementation Guide: Re-index Pipeline (FEAT-MEM-07)

Deterministic re-index of guardkit's authoritative markdown corpus into typed
payloads, published through the **live relay (FEAT-MEM-04)** into the
**deterministic writer (FEAT-MEM-03)**, plus a reviewed backfill staging gate.

**Governing decisions:** ADR-SP-007 (markdown is authoritative; the store is an
index; fixes route to source + re-index) and DECISION-DF-001 (Fable for offline
authoring only; zero cloud/frontier model on any runtime publish path).

**The load-bearing insight:** idempotency, versioned upsert, and natural-key
dedup are **enforced downstream** by the writer's content-hash upsert. The
pipeline does not implement dedup — its job is path-safe walk, deterministic
parse, faithful publish, honest accounting, and the operator review gate.

---

## Data Flow: Read/Write Paths

```mermaid
flowchart LR
    subgraph Writes["Write Paths (this feature)"]
        W1["reindex.pipeline.reindex_corpus()\n(TASK-RIP-005)"]
        W2["reindex.backfill gate\n(TASK-RIP-006)"]
        P["reindex.publisher\n(TASK-RIP-002)"]
    end

    subgraph Storage["Storage (existing — FEAT-MEM-03/04)"]
        ST[("MEMORY stream\n(NATS JetStream)")]
        RW["RelayService._ingest_json\n→ DeterministicWriter\n(content-hash upsert)"]
        DB[("Postgres + pgvector\n(records by natural_key)")]
        DLQ[("dead-letter subject")]
    end

    subgraph Reads["Read Paths (this feature)"]
        R1["reindex.audit\n(TASK-RIP-007)"]
        R2["reindex.parity\n(TASK-RIP-008)"]
    end

    W1 -->|"typed payload"| P
    W2 -->|"reviewed payload"| P
    P -->|"MemoryEpisodeV1 json+payload_type"| ST
    ST -->|"relay consumes"| RW
    RW -->|"upsert"| DB
    RW -.->|"PoisonEpisodeError"| DLQ

    DB -->|"record_identity lookup"| R1
    DLQ -->|"DLQ records"| R1
    DB -->|"probe_harness search"| R2

    style W2 fill:#ffc,stroke:#990
    style R1 fill:#cfc,stroke:#090
    style R2 fill:#cfc,stroke:#090
```

_What to look for: every write path (re-index + reviewed backfill) funnels through
the **single publisher** (TASK-RIP-002) onto the MEMORY stream — no second write
path. Both read paths (audit, parity) have callers and are wired._

**Disconnection check:** ✅ No disconnected paths. Both read paths (audit →
TASK-RIP-007, parity → TASK-RIP-008) have explicit callers; both write paths
converge on the same publisher. The single-write-path invariant (TASK-RIP-006
reuses TASK-RIP-002) is the deliberate "no second code path" design from the spec.

---

## Integration Contracts (sequence)

```mermaid
sequenceDiagram
    participant W as Walker (RIP-001)
    participant C as Classify/Dispatch (RIP-003)
    participant Pa as Parsers (RIP-004)
    participant O as Orchestrator (RIP-005)
    participant Pu as Publisher (RIP-002)
    participant R as RelayService (existing)
    participant Wr as DeterministicWriter (existing)

    O->>W: walk_corpus(root)
    W-->>O: CorpusDocument(path, text)
    O->>C: classify(document)
    C-->>O: kind | unrecognized | parse_failure
    O->>Pa: parse(document, kind)
    Pa-->>O: BasePayload  [project/identifier underscored, source_ref set]
    O->>Pu: publish(payload)
    Pu->>R: MemoryEpisodeV1(content_format="json", payload_type=...)
    R->>Wr: write(payload)  [content-hash upsert — idempotent]
    Wr-->>R: committed
    Note over O,Wr: Idempotency/dedup live HERE (downstream), not in the pipeline
    Note over Pa,Pu: CONTRACT typed_payload — identifiers MUST be ^[a-zA-Z0-9_]+$
    Note over Pu,R: CONTRACT memory_episode_routing — json + payload_type or it mis-routes/DLQs
```

_What to look for: the two `Note over` markers are the two §4 contracts. The
fetch-then-publish chain never "fetches then discards" — every parsed payload is
handed to the publisher; unparseable/unrecognized documents return to the
orchestrator's `RunReport` (accounted, not dropped)._

---

## Task Dependencies

```mermaid
graph TD
    T1["RIP-001 walker"] --> T3["RIP-003 classify/dispatch"]
    T3 --> T4["RIP-004 parsers"]
    T2["RIP-002 publisher"] --> T5["RIP-005 orchestrator"]
    T4 --> T5
    T5 --> T6["RIP-006 backfill gate"]
    T5 --> T7["RIP-007 audit"]
    T5 --> T8["RIP-008 parity report"]
    T2 --> T6
    T5 --> T9["RIP-009 CLI"]
    T6 --> T9
    T6 --> T10["RIP-010 integration tests"]
    T7 --> T10
    T8 --> T10
    T9 --> T10
    T9 --> T11["RIP-011 operator run"]
    T10 --> T11

    style T1 fill:#cfc,stroke:#090
    style T2 fill:#cfc,stroke:#090
    style T6 fill:#cfc,stroke:#090
    style T7 fill:#cfc,stroke:#090
    style T8 fill:#cfc,stroke:#090
    style T11 fill:#fcc,stroke:#c00
```

_Green = parallel-safe within its wave. Red (RIP-011) = `operator_handoff`,
AutoBuild skips it._

### Execution waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | RIP-001, RIP-002 | walker + publisher (independent) — parallel |
| 2 | RIP-003 | classify/dispatch |
| 3 | RIP-004 | typed parsers |
| 4 | RIP-005 | orchestrator + run report |
| 5 | RIP-006, RIP-007, RIP-008 | backfill gate, audit, parity — parallel |
| 6 | RIP-009 | CLI entrypoint |
| 7 | RIP-010 | integration tests (ephemeral Postgres) |
| 8 | RIP-011 | **operator_handoff** — live verification, AutoBuild skips |

---

## §4: Integration Contracts

### Contract: typed_payload
- **Producer task:** TASK-RIP-004 (deterministic parsers)
- **Consumer task(s):** TASK-RIP-005 (orchestrator)
- **Artifact type:** in-process Python object — `BasePayload` subclass
- **Format constraint:** `project` and `identifier` must match `^[a-zA-Z0-9_]+$`
  (`IDENTIFIER_PATTERN` in [payloads/base.py](src/fleet_memory/payloads/base.py)).
  Guardkit IDs carry hyphens/colons (`ADR-SP-007`, `FEAT-MEM-07`) and **must be
  normalized to underscores** (`ADR_SP_007`, `FEAT_MEM_07`) by the parser, or
  `BasePayload.__init__` raises `IdentifierValidationError`. `source_ref` is
  required; `payload_type` must be a key in the registry.
- **Validation method:** Coach verifies a parser unit test asserts normalized
  identifiers (`test_hyphenated_guardkit_id_normalized_to_underscores`) and that a
  bad identifier becomes an unparseable result, not an escaped exception.

### Contract: memory_episode_routing
- **Producer task:** TASK-RIP-002 (episode publisher)
- **Consumer task(s):** TASK-RIP-005 (orchestrator), TASK-RIP-006 (backfill gate)
- **Artifact type:** NATS message — `MemoryEpisodeV1` on the MEMORY stream
- **Format constraint:** `content_format` must be the literal `"json"` **and**
  `payload_type` must be a registered type, so `RelayService.ingest` routes the
  episode to `DeterministicWriter` ([relay/service.py](src/fleet_memory/relay/service.py)
  `_ingest_json`). Any other `content_format` routes to the prose chunker (silent
  wrong-path) or DLQs as an unknown type.
- **Validation method:** Coach verifies the seam test in TASK-RIP-005 /
  TASK-RIP-006 (`@pytest.mark.integration_contract("memory_episode_routing")`)
  asserts `content_format == "json"`, `payload_type` is set, and the body
  round-trips through `get_model_for_type`.

⚠️ These two contracts are the integration-boundary hot spots. The identifier
normalization (Contract `typed_payload`) is the single most likely silent failure:
real guardkit IDs are hyphenated and will be rejected downstream unless the parser
normalizes them.

---

## Notes for the implementer

- **Reuse, don't rebuild:** publisher reuses the broker wiring in
  [app.py](src/fleet_memory/app.py); parity reuses
  [retrieval/probe_harness.py](src/fleet_memory/retrieval/probe_harness.py);
  audit resolves identity via [writer/identity.py](src/fleet_memory/writer/identity.py).
- **Single write path:** TASK-RIP-006 must import TASK-RIP-002's publisher, never
  fork a parallel publish path.
- **Hermetic tests:** unit tests use a fake publisher; integration tests use the
  ephemeral `deploy/local/` Postgres (no NAS dependency). Only TASK-RIP-011 touches
  live infrastructure.
