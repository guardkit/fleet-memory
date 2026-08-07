"""Configuration settings for fleet-memory service."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Fleet-memory service configuration loaded from environment variables.

    All settings are loaded from environment variables with the FLEET_MEMORY_ prefix.
    Required fields must be provided via environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="FLEET_MEMORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required fields
    pg_dsn: str = Field(..., description="PostgreSQL connection DSN")
    embed_url: str = Field(..., description="Embedding service URL")

    # Corpus configuration
    corpus_root: str = Field(
        default="./corpus",
        description="Root directory for corpus documents (FLEET_MEMORY_CORPUS_ROOT)",
    )

    # Backfill configuration
    backfill_dir: str = Field(
        default="backfill/staging/",
        description="Directory for backfill staging payloads (FLEET_MEMORY_BACKFILL_DIR)",
    )

    # Reindex publish path configuration
    publish_nats_url: str = Field(
        default="",
        description=(
            "NATS URL the reindex publisher connects to — consumed ONLY by the reindex "
            "publish path (ReindexPublisher owns its own JetStream connection; it never "
            "touches fleet_memory.app.broker). Publish runs fail loud BEFORE walking "
            "when unset (FLEET_MEMORY_PUBLISH_NATS_URL)"
        ),
    )
    corpus_manifest: str = Field(
        default="",
        description=(
            "Path to the corpus manifest JSON exported by guardkit "
            "(python -m guardkit.memory.harvest_taxonomy --json). The reindex pipeline "
            "walks ONLY the manifest's reindex-owned directories "
            "(FLEET_MEMORY_CORPUS_MANIFEST)"
        ),
    )

    # Chronicler batch harvester (WS4-S7). The Chronicler is a BATCH JOB, not a resident
    # consumer (the relay's operational record argues against another resident consumer,
    # WS4 §4.2); it reads the durable store and emits two DF-008-split outputs.
    chronicler_dataset_intake_dir: str = Field(
        default="chronicler_out/dataset_intake",
        description=(
            "Directory the Chronicler writes flywheel-tagged dataset rows (JSONL) into — "
            "point at the agentic-dataset-factory intake in deployment. Rows are PRIVATE "
            "and Coach-validated before joining any training set "
            "(FLEET_MEMORY_CHRONICLER_DATASET_INTAKE_DIR)"
        ),
    )
    chronicler_story_card_queue_dir: str = Field(
        default="chronicler_out/story_card_queue",
        description=(
            "Directory the Chronicler writes DRAFT story-card markdown into — the human "
            "review queue. Cards are the ONLY output that may cross the publication "
            "boundary, and only through the human gate (DF-008) "
            "(FLEET_MEMORY_CHRONICLER_STORY_CARD_QUEUE_DIR)"
        ),
    )
    chronicler_public_projects: str = Field(
        default="",
        description=(
            "Comma-separated allowlist of projects whose story cards are non-confidential. "
            "Any project NOT listed is marked confidential (DF-008: client-work events "
            "must be structurally unable to leak) (FLEET_MEMORY_CHRONICLER_PUBLIC_PROJECTS)"
        ),
    )
    chronicler_scan_limit: int = Field(
        default=1000,
        gt=0,
        description=(
            "Max records scanned per (project, payload_type) namespace in one harvest "
            "run (FLEET_MEMORY_CHRONICLER_SCAN_LIMIT)"
        ),
    )

    # Embedding configuration
    embed_model: str = Field(
        default="nomic-embed-text-v1.5",
        description="Embedding model name",
    )
    embed_dims: int = Field(
        default=768,
        description="Embedding vector dimensions",
    )
    embed_timeout_s: float = Field(
        default=180.0,
        description="Embedding service timeout in seconds. Sized to absorb a cold-start of "
        "the embed model on a shared/evicting llama-swap server (FEAT-HARV observed "
        "85-181s cold-starts) so a single request completes without a spurious timeout "
        "that would nak/DLQ a recoverable failure. MUST stay < ack_wait_s.",
    )
    embed_max_batch_tokens: int = Field(
        default=2048,
        gt=0,
        description="Max estimated tokens packed into a single /v1/embeddings request "
        "(TASK-FIX-RELAYBATCH01). The embed client greedily sub-batches inputs so no "
        "request exceeds this budget; an episode's chunks are spread across as many "
        "requests as needed instead of one unbounded batch. MUST stay <= the embed "
        "server's effective per-slot n_ctx (Qwen3-Embedding deploy: 8192/slot; nomic: "
        "2048 hard), ideally with headroom to absorb token-estimation error.",
    )

    # PostgreSQL pool configuration
    pg_pool_min: int = Field(
        default=2,
        description="Minimum PostgreSQL pool connections",
    )
    pg_pool_max: int = Field(
        default=10,
        description="Maximum PostgreSQL pool connections (ASSUM-004 placeholder)",
    )
    pg_connect_timeout_s: float = Field(
        default=10.0,
        description="PostgreSQL connection timeout in seconds (ASSUM-006 placeholder)",
    )

    # NATS configuration
    nats_url: str = Field(
        default="nats://localhost:4222",
        description="NATS server URL",
    )

    # MCP server transport (stdio for spawned clients, http for the resident service)
    mcp_transport: str = Field(
        default="stdio",
        description="MCP transport: 'stdio' or 'http' (FLEET_MEMORY_MCP_TRANSPORT)",
    )
    mcp_host: str = Field(
        default="127.0.0.1",
        description="Bind address for http transport (FLEET_MEMORY_MCP_HOST)",
    )
    mcp_port: int = Field(
        default=8005,
        description="Bind port for http transport (FLEET_MEMORY_MCP_PORT)",
    )
    mcp_allowed_hosts: str = Field(
        default="",
        description="Comma-separated extra Host-header values accepted by the http "
        "transport (e.g. 'promaxgb10-41b1:8005'). Needed when clients reach the "
        "resident service by hostname rather than localhost "
        "(FLEET_MEMORY_MCP_ALLOWED_HOSTS)",
    )

    # DLQ configuration
    dlq_subject: str = Field(
        default="memory.dlq",
        description="Dead-letter subject PREFIX (ASSUM-006); the handler publishes poison "
        "per-project to {dlq_subject}.{project_id} (e.g. memory.dlq.guardkit), captured by "
        "the MEMORY stream's memory.dlq.> subjects",
    )
    max_deliver: int = Field(
        default=5,
        description="Maximum delivery attempts before parking (ASSUM-005)",
    )
    ack_wait_s: int = Field(
        default=1200,
        description="JetStream ack_wait for the durable consumer, in seconds. MUST exceed "
        "the worst-case single-episode embed+commit time: a large multi-chunk episode "
        "embeds AND writes every chunk to Postgres before the ack, so a 70+-chunk episode "
        "against the NAS Postgres can take many minutes. If ack_wait expires mid-processing "
        "the episode is redelivered and reprocessed from scratch forever (FEAT-HARV "
        "recovery, 2026-06-27). Raised from the v2 default of 60. MUST stay > embed_timeout_s.",
    )

    # Liveness fence (ladder ⑦). The structural "never dark again" guarantee: the
    # memory flywheel once went dark for a month and nothing said so. Two checks run
    # on a timer — the newest row in the store aging past a limit, and the relay
    # ingesting nothing while builds are finishing. One rule, one place: the relay
    # (which WRITES the progress marker) and the checker (which READS it) both take
    # the path from fence_relay_marker_path; neither restates the default.
    fence_store_max_age_hours: int = Field(
        default=168,
        gt=0,
        description=(
            "Alarm when the newest row in the store is older than this many hours. "
            "Default 168 (a dark week): long enough to tolerate a quiet weekend plus "
            "a bank holiday, short enough that a real blackout is caught in days "
            "rather than a month (FLEET_MEMORY_FENCE_STORE_MAX_AGE_HOURS)"
        ),
    )
    fence_build_window_hours: int = Field(
        default=72,
        gt=0,
        description=(
            "How far back the relay-idle check looks for finished builds. The alarm "
            "sentence is 'three or more builds finished in the last three days and "
            "memory recorded nothing in that time' (FLEET_MEMORY_FENCE_BUILD_WINDOW_HOURS)"
        ),
    )
    fence_min_builds_in_window: int = Field(
        default=3,
        gt=0,
        description=(
            "How many finished builds must sit inside the window before relay silence "
            "counts as an alarm. One build proves nothing; three across three days is a "
            "pattern (FLEET_MEMORY_FENCE_MIN_BUILDS_IN_WINDOW)"
        ),
    )
    fence_relay_restart_grace_minutes: int = Field(
        default=75,
        ge=0,
        description=(
            "Grace period after a relay restart before relay silence counts. A container "
            "recreate orphans an in-flight delivery until ack_wait expires (~1h by "
            "record); 75 minutes covers that with slack. Applies ONLY to the relay-idle "
            "check (FLEET_MEMORY_FENCE_RELAY_RESTART_GRACE_MINUTES)"
        ),
    )
    fence_watch_projects: str = Field(
        default="guardkit",
        description=(
            "Comma-separated projects given their own max-age check on top of the "
            "whole-store one. 'jarvis' is deliberately absent: its writer is dark by "
            "record, so it would alarm truthfully but uselessly every run — add it once "
            "re-armed (FLEET_MEMORY_FENCE_WATCH_PROJECTS)"
        ),
    )
    fence_builds_dir: str = Field(
        default="~/forge-state/receipts",
        description=(
            "Directory of forge build receipts. The fence reads only the directory "
            "NAMES (build-FEAT-<id>-<YYYYMMDDHHMMSS>) — no database, no file lock "
            "(FLEET_MEMORY_FENCE_BUILDS_DIR)"
        ),
    )
    fence_relay_marker_path: str = Field(
        default="~/.local/state/fleet-memory/relay-progress.json",
        description=(
            "The relay's progress marker. The relay writes it after every message; the "
            "fence reads it. This is the ONLY progress signal the relay emits — a clean "
            "ingest is otherwise completely silent (FLEET_MEMORY_FENCE_RELAY_MARKER_PATH)"
        ),
    )
    fence_state_dir: str = Field(
        default="~/.local/state/fleet-memory",
        description=(
            "Where the fence writes its status file, its alarm log, and where it looks "
            "for an acknowledgement file (FLEET_MEMORY_FENCE_STATE_DIR)"
        ),
    )

    # Chunking configuration
    chunk_target_tokens: int = Field(
        default=1000,
        description="Target chunk size in tokens for prose chunking (OD-1)",
    )
    chunk_overlap_ratio: float = Field(
        default=0.15,
        description="Overlap ratio for prose chunks (0.0-1.0)",
    )

    @field_validator("pg_dsn", "embed_url")
    @classmethod
    def validate_not_empty(cls, v: str, info) -> str:
        """Ensure required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v
