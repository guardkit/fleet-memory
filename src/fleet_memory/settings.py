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
        default=10.0,
        description="Embedding service timeout in seconds (ASSUM-008 placeholder)",
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
