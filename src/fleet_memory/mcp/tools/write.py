"""memory_write_payload MCP tool: typed payload write through DeterministicWriter.

Exposes memory_write_payload as an MCP tool that validates typed payloads at the
boundary, instantiates registered models via the payload registry, and dispatches
through the existing DeterministicWriter.write — the single write path.

There is no second write path: the tool produces records byte-identical to a relay
write of the same payload.

Producer: TASK-MCP-004
Consumer: Wave-3 MCP integration
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from fleet_memory.errors import PoisonEpisodeError, TransientIngestError
from fleet_memory.mcp.degradation import ToolResult, _sanitize_message, tool_safe
from fleet_memory.mcp.doors import check_door_project
from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.relay.schema import MAX_ENVELOPE_BYTES, SUBJECT_TOKEN_RE, MemoryEpisodeV1

if TYPE_CHECKING:
    from fleet_memory.relay.service import RelayService
    from fleet_memory.writer.core import DeterministicWriter

# THE SANDBOX'S NARROW DOOR (15 October 2026). Code in a build can reach the
# sandbox's door, so a write there must not plant records where the factory or
# its agents will read them as their own. These are the factory's and its
# agents' shelves (memory projects); the narrow door never writes on them. The
# match is exact after lower-casing, as searches are exact. The list is in code
# so that adding a product changes nothing; a new agent shelf needs a release.
RESERVED_PROJECTS = (
    "guardkit",
    "guardkitfactory",
    "forge",
    "fleet_memory",
    "nats_core",
    "specialist_agent",
    "jarvis",
    "office_manager",
    "ai_transition",
    "software_factory",
)

SANDBOX_REFUSAL = (
    "the sandbox's memory door accepts only build outcomes that replace nothing, "
    f"and never on the factory's own shelves ({', '.join(RESERVED_PROJECTS)})"
)


@tool_safe
async def memory_write_payload(
    payload_dict: dict[str, Any],
    writer: DeterministicWriter,
    sandbox: bool = False,
    allowed_projects: frozenset[str] | None = None,
) -> str:
    """Write a typed payload through the deterministic writer.

    Validates the payload at the boundary, resolves the type through the registry,
    instantiates the typed model (ignoring any forged identity fields), and
    dispatches to DeterministicWriter.write.

    On success returns the derived natural key (type:project:identifier).
    Idempotency and content-hash upsert are inherited from the writer.

    Args:
        payload_dict: Raw payload dict from MCP client (must include payload_type)
        writer: DeterministicWriter instance from ServerContext
        sandbox: True on the sandbox's narrow door, which writes only a
            build_outcome with no supersedes, never on RESERVED_PROJECTS
        allowed_projects: on a sandbox's own door, the only projects it writes
            for, on top of the narrow door's rules; None writes for any project

    Returns:
        The derived natural key (e.g., "adr:my_project:ADR_001")

    Raises:
        ValueError: If payload_type is unknown or validation fails
        IdentifierValidationError: If identifier contains invalid characters
        ValidationError: If required fields are missing
        TimeoutError: If store is unreachable (mapped to infrastructure error)
        EmbedServiceError: If embeddings are unavailable (mapped to infrastructure error)
    """
    # Step 1: Extract and validate payload_type
    if "payload_type" not in payload_dict:
        raise ValueError(
            "payload_type is required: every write must specify a registered payload type"
        )

    payload_type = payload_dict["payload_type"]

    # Step 2: Resolve type through registry (raises UnknownPayloadTypeError if not found)
    model_class = get_model_for_type(payload_type)

    # Step 3: Instantiate typed model (validates all fields, ignores extra like stored_identity)
    # This will raise ValidationError if required fields are missing or invalid
    # IdentifierValidationError will be raised by the model's validators if identifier is invalid
    try:
        payload = model_class(**payload_dict)
    except ValidationError as exc:
        # Convert Pydantic validation error to readable message
        errors = exc.errors()
        if errors:
            first_error = errors[0]
            field = first_error.get("loc", ["unknown"])[0]
            msg = first_error.get("msg", "validation failed")
            raise ValueError(f"Field '{field}' {msg}") from exc
        raise ValueError("Payload validation failed") from exc

    # Step 3b: the narrow door checks the validated record before the writer
    if sandbox and (
        payload.payload_type != "build_outcome"
        or payload.supersedes
        or payload.project.lower() in RESERVED_PROJECTS
    ):
        raise ValueError(SANDBOX_REFUSAL)
    # Step 3c: a sandbox's own door writes only for its own projects (17 October 2026)
    check_door_project(payload.project, allowed_projects)

    # Step 4: Write through the deterministic writer (single write path)
    # Idempotency, content-hash upsert, and supersession are handled by the writer
    await writer.write(payload)

    # Step 5: Return derived natural key as acknowledgment (ASSUM-006)
    # This is the server-derived identity, never a client-supplied value
    return payload.natural_key


async def memory_publish_envelope(
    envelope: dict[str, Any],
    service: RelayService,
) -> ToolResult:
    """Ingest one published memory envelope exactly as the relay ingests it.

    WHY THIS EXISTS (14 October 2026). A build sandbox holds no bus password.
    Typed records already have a way in without the bus (memory_write_payload),
    but prose records (turn states, specs and the other document groups) have
    no typed form: the publisher sends them as a ``MemoryEpisodeV1`` envelope
    with ``content_format`` markdown or text, and the relay chunks them into
    the store. This takes that same envelope and hands it to the relay's own
    ``RelayService.ingest``, so there is one ingestion path and one storage
    format. Typed json envelopes take the relay's typed path the same way.

    The envelope is parsed with the relay's own ``MemoryEpisodeV1`` model.
    What the relay would dead-letter (a poison episode) comes back as a client
    error; what it would redeliver (a transient failure) comes back as an
    infrastructure error, for the caller to retry or report. Nothing is
    written in either case beyond what the relay itself would have written.

    The bus-only parts of the relay are not here: acknowledgements, the
    dead-letter subject and the relay's liveness marker belong to messages
    that arrived over the bus.

    Returns:
        ``ToolResult`` with ``value`` ``{"episode_id": ...}`` on success.
    """
    try:
        episode = MemoryEpisodeV1.model_validate(envelope)
    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            field = ".".join(str(part) for part in errors[0].get("loc", ["unknown"]))
            message = f"Field '{field}' {errors[0].get('msg', 'validation failed')}"
        else:
            message = "Envelope validation failed"
        return ToolResult(is_error=True, error_type="client", message=_sanitize_message(message))

    # THE BUS'S OWN LIMITS (14 October 2026). The relay only ever sees what the bus
    # could carry, so it checks neither. The door bypasses the bus, so it applies
    # both, and takes nothing the bus route could not have delivered.
    size = len(episode.model_dump_json().encode("utf-8"))
    if size > MAX_ENVELOPE_BYTES:
        return ToolResult(
            is_error=True,
            error_type="client",
            message=(
                f"the envelope is {size} bytes, over the {MAX_ENVELOPE_BYTES} byte limit "
                "the bus keeps; chunk the content before sending it"
            ),
        )
    for field_name in ("project_id", "episode_type"):
        if not SUBJECT_TOKEN_RE.match(getattr(episode, field_name)):
            return ToolResult(
                is_error=True,
                error_type="client",
                message=(
                    f"{field_name} must be a plain subject token (letters, digits, "
                    "'-' and '_', starting with a letter or digit), as the bus requires"
                ),
            )

    try:
        await service.ingest(episode)
    except PoisonEpisodeError as exc:
        message = exc.reason if not exc.detail else f"{exc.reason} ({exc.detail})"
        return ToolResult(is_error=True, error_type="client", message=_sanitize_message(message))
    except TransientIngestError as exc:
        return ToolResult(
            is_error=True,
            error_type="infrastructure",
            message=_sanitize_message(exc.message),
        )
    return ToolResult(is_error=False, value={"episode_id": episode.episode_id})


def register(
    mcp, context, sandbox: bool = False, allowed_projects: frozenset[str] | None = None
) -> None:
    """Register the memory_write_payload tool with the FastMCP server.

    Extension point implementation for TASK-MCP-001.

    Args:
        mcp: FastMCP server instance
        context: ServerContext with dependencies
        sandbox: True for the sandbox's narrow door: the write is checked
            (see RESERVED_PROJECTS) and memory_publish_envelope is not offered
        allowed_projects: a sandbox's own door (needs ``sandbox``): the only
            projects the write accepts
    """

    # Canonical name — matches the command specs' mcp__fleet_memory__memory_write_payload
    @mcp.tool(name="memory_write_payload")
    async def memory_write_payload_tool(payload: dict) -> dict:
        """Write a typed memory payload through the deterministic writer.

        Validates the payload at the boundary, resolves the type through the registry,
        and writes to the memory store. Returns the derived natural key on success.

        Args:
            payload: Dictionary with payload_type and type-specific fields

        Returns:
            Success: ToolResult with natural_key value
            Error: ToolResult with error details
        """
        # Writer comes from the shared ServerContext the lifespan populates
        writer = context.writer

        if writer is None:
            return {
                "is_error": True,
                "error_type": "infrastructure",
                "message": "The memory writer is unavailable",
            }

        # Call the wrapped implementation
        result = await memory_write_payload(
            payload, writer, sandbox=sandbox, allowed_projects=allowed_projects
        )

        # Return ToolResult directly (FastMCP will serialize it)
        return result

    if sandbox:
        return

    # The relay's own ingestion, for an envelope that only the bus could carry
    # (prose records), from a caller with no bus account (a build sandbox).
    @mcp.tool(name="memory_publish_envelope")
    async def memory_publish_envelope_tool(envelope: dict) -> dict:
        """Ingest one memory envelope exactly as the relay ingests it from the bus.

        Args:
            envelope: A MemoryEpisodeV1 envelope, as the publisher puts it on the bus

        Returns:
            Success: ToolResult with {"episode_id": ...}
            Error: ToolResult with error details
        """
        from fleet_memory.relay.chunk_writer import ChunkWriter
        from fleet_memory.relay.service import RelayService

        if context.store is None or context.writer is None or context.settings is None:
            return {
                "is_error": True,
                "error_type": "infrastructure",
                "message": "The memory store is unavailable",
            }
        # Built the way the relay's own lifespan builds it (fleet_memory.app),
        # over this server's store, writer and settings.
        service = RelayService(
            writer=context.writer,
            chunk_writer=ChunkWriter(store=context.store),
            settings=context.settings,
        )
        return await memory_publish_envelope(envelope, service)
