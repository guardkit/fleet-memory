"""Exceptions for fleet-memory embedding operations.

## Exception Taxonomy for Relay Handlers

When processing episodes from NATS subjects, exceptions are classified into two
mutually exclusive categories that determine retry vs dead-letter behavior:

1. **PoisonEpisodeError**: Deterministic, non-recoverable failures. The episode
   will never succeed on redelivery and must be parked on the DLQ. Examples:
   unparseable body, unknown payload_type, payload validation failure,
   unrecognized content_format, hyphenated/invalid project, wrong-dimension
   embedding (EmbedDimensionError), deterministic embed rejection
   (EmbedRequestError — a 4xx such as exceed_context_size_error that will
   fail identically on every retry).

2. **TransientIngestError**: Recoverable downstream failures. Must be
   negatively-acknowledged for redelivery, never dead-lettered. Examples:
   embedding service unavailable (EmbedServiceError: 5xx, malformed response,
   408/429), store unreachable, connection drop, timeout (EmbedTimeoutError).

**Default-to-transient policy**: Any *unenumerated* exception escaping the
service layer is treated as transient (nak + redeliver), never as poison.
Losing data is worse than redelivering.
"""


class EmbedDimensionError(ValueError):
    """Raised when embedding dimensions don't match expected dimensions.

    Error message includes both actual and expected dimensions.
    Never includes database credentials.
    """

    def __init__(self, actual: int, expected: int) -> None:
        """Initialize with actual and expected dimensions.

        Args:
            actual: The actual dimension count received
            expected: The expected dimension count from settings
        """
        super().__init__(
            f"Embedding dimension mismatch: got {actual} dimensions, expected {expected}"
        )
        self.actual = actual
        self.expected = expected


class EmbedTimeoutError(TimeoutError):
    """Raised when embedding service request times out.

    May include the embedding service URL but never database credentials.
    """

    def __init__(self, url: str, timeout_s: float) -> None:
        """Initialize with service URL and timeout value.

        Args:
            url: The embedding service URL (safe to log)
            timeout_s: The timeout threshold in seconds
        """
        super().__init__(f"Embedding service request timed out after {timeout_s}s: {url}")
        self.url = url
        self.timeout_s = timeout_s


class EmbedServiceError(RuntimeError):
    """Raised when embedding service returns an error.

    Covers HTTP errors, malformed JSON, and other service failures.
    May include the embedding service URL but never database credentials.
    """

    def __init__(
        self, message: str, url: str | None = None, status_code: int | None = None
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error description
            url: Optional embedding service URL (safe to log)
            status_code: Optional HTTP status code
        """
        msg = f"Embedding service error: {message}"
        if status_code is not None:
            msg += f" (HTTP {status_code})"
        if url is not None:
            msg += f" - {url}"
        super().__init__(msg)
        self.url = url
        self.status_code = status_code


class EmbedRequestError(EmbedServiceError):
    """Raised when the embedding service rejects a request *deterministically*.

    A client-side (HTTP 4xx) rejection that will fail identically on every
    redelivery — e.g. ``exceed_context_size_error`` when an input exceeds the
    server's per-slot n_ctx. Distinguished from its parent ``EmbedServiceError``
    (transient: 5xx, malformed response, network) so the relay can route it to the
    DLQ as a *poison* failure rather than nak-retrying it until max_deliver
    silently drops it (TASK-FIX-RELAYDROP01).

    NOT every 4xx is deterministic: 408 (Request Timeout) and 429 (Too Many
    Requests) are transient and stay ``EmbedServiceError``.

    Subclasses ``EmbedServiceError`` so read-path callers that catch the parent
    (search/retrieval degradation) keep working; the relay catches this *first*,
    before the transient clause, to classify it as poison.

    May include the embedding service URL and the server's error ``type`` but
    never database credentials.
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error description (e.g. the server's message)
            url: Optional embedding service URL (safe to log)
            status_code: HTTP status code of the rejected request (a 4xx)
            error_type: Optional server-supplied error type (e.g.
                ``exceed_context_size_error``), recorded on the DLQ for diagnosis
        """
        if error_type:
            message = f"{message} [{error_type}]"
        super().__init__(message, url=url, status_code=status_code)
        self.error_type = error_type


class NamespaceValidationError(ValueError):
    """Raised when namespace tuple contains invalid identifiers.

    Namespace identifiers must match ^[a-z0-9_]+$ (underscores only, no hyphens).
    Never includes database credentials.
    """

    def __init__(self, namespace: tuple[str, ...], invalid_parts: list[str]) -> None:
        """Initialize with namespace and invalid parts.

        Args:
            namespace: The full namespace tuple that failed validation
            invalid_parts: List of invalid identifier strings
        """
        super().__init__(
            f"Invalid namespace identifiers {invalid_parts}: must use underscores only "
            f"(match ^[a-z0-9_]+$), got namespace {namespace}"
        )
        self.namespace = namespace
        self.invalid_parts = invalid_parts


class UnknownPayloadTypeError(ValueError):
    """Raised when payload_type lookup fails in the dispatch registry.

    The registry only recognizes canonical payload types.
    Lookup is case-sensitive; no silent fallback to Document (ASSUM-010).
    """

    def __init__(self, payload_type: str) -> None:
        """Initialize with the unknown payload type name.

        Args:
            payload_type: The unrecognized type name that was rejected
        """
        super().__init__(
            f"Unknown payload type '{payload_type}': not found in dispatch registry. "
            f"Lookup is case-sensitive."
        )
        self.payload_type = payload_type


class PoisonEpisodeError(Exception):
    """Raised when an episode has a deterministic, non-recoverable failure.

    The episode will never succeed on redelivery and must be parked on the DLQ.
    Triggers dead-letter behavior in the relay handler (TASK-RLY-006).

    Examples: unparseable body, unknown payload_type, payload validation failure,
    unrecognized content_format, hyphenated/invalid project, wrong-dimension embedding.

    Never includes database credentials.
    """

    def __init__(self, reason: str, detail: str | None = None) -> None:
        """Initialize with reason and optional detail.

        Args:
            reason: Human-readable failure reason suitable for DLQ recording
            detail: Optional additional diagnostic information
        """
        msg = f"Poison episode: {reason}"
        if detail is not None:
            msg += f" - {detail}"
        super().__init__(msg)
        self.reason = reason
        self.detail = detail


class TransientIngestError(Exception):
    """Raised when a recoverable downstream failure occurs.

    Must be negatively-acknowledged for redelivery, never dead-lettered.
    Triggers nak behavior in the relay handler (TASK-RLY-006).

    Examples: embedding service unavailable, store unreachable, connection drop,
    timeout during external service call.

    Never includes database credentials.
    """

    def __init__(self, message: str) -> None:
        """Initialize with error message.

        Args:
            message: Human-readable description of the transient failure
        """
        super().__init__(f"Transient ingest error: {message}")
        self.message = message
