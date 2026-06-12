"""Exceptions for fleet-memory embedding operations."""


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
