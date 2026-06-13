"""Unit tests for relay exception taxonomy.

Verifies PoisonEpisodeError vs TransientIngestError distinction per TASK-RLY-002.
"""

from __future__ import annotations

import pytest


def test_import_poison_episode_error() -> None:
    """PoisonEpisodeError can be imported from fleet_memory.errors."""
    from fleet_memory.errors import PoisonEpisodeError

    assert PoisonEpisodeError is not None


def test_import_transient_ingest_error() -> None:
    """TransientIngestError can be imported from fleet_memory.errors."""
    from fleet_memory.errors import TransientIngestError

    assert TransientIngestError is not None


def test_poison_episode_error_subclasses_exception() -> None:
    """PoisonEpisodeError subclasses Exception (standard error base)."""
    from fleet_memory.errors import PoisonEpisodeError

    assert issubclass(PoisonEpisodeError, Exception)


def test_transient_ingest_error_subclasses_exception() -> None:
    """TransientIngestError subclasses Exception (standard error base)."""
    from fleet_memory.errors import TransientIngestError

    assert issubclass(TransientIngestError, Exception)


def test_poison_episode_error_carries_reason() -> None:
    """PoisonEpisodeError carries a reason string suitable for DLQ recording."""
    from fleet_memory.errors import PoisonEpisodeError

    error = PoisonEpisodeError(reason="unparseable body")
    assert error.reason == "unparseable body"
    assert "unparseable body" in str(error)


def test_poison_episode_error_carries_optional_detail() -> None:
    """PoisonEpisodeError optionally carries additional detail."""
    from fleet_memory.errors import PoisonEpisodeError

    error = PoisonEpisodeError(reason="validation failed", detail="missing required field 'project'")
    assert error.reason == "validation failed"
    assert hasattr(error, "detail")
    assert error.detail == "missing required field 'project'"


def test_poison_episode_error_detail_is_optional() -> None:
    """PoisonEpisodeError detail parameter is optional."""
    from fleet_memory.errors import PoisonEpisodeError

    error = PoisonEpisodeError(reason="unknown payload_type")
    assert error.reason == "unknown payload_type"
    # detail should be None or not set when not provided
    assert getattr(error, "detail", None) is None


def test_transient_ingest_error_has_message() -> None:
    """TransientIngestError carries a descriptive message."""
    from fleet_memory.errors import TransientIngestError

    error = TransientIngestError("embedding service unavailable")
    assert "embedding service unavailable" in str(error)


def test_exceptions_are_not_in_same_subtree() -> None:
    """PoisonEpisodeError and TransientIngestError are not in the same subtree.

    This prevents accidentally catching one as the other.
    A TransientIngestError must NOT be catchable as PoisonEpisodeError.
    A PoisonEpisodeError must NOT be catchable as TransientIngestError.
    """
    from fleet_memory.errors import PoisonEpisodeError, TransientIngestError

    # Neither should be a subclass of the other
    assert not issubclass(PoisonEpisodeError, TransientIngestError)
    assert not issubclass(TransientIngestError, PoisonEpisodeError)

    # Verify exception handling behavior
    poison = PoisonEpisodeError(reason="test")
    transient = TransientIngestError("test")

    # Trying to catch poison as transient should fail
    with pytest.raises(PoisonEpisodeError):
        try:
            raise poison
        except TransientIngestError:
            pytest.fail("PoisonEpisodeError should not be catchable as TransientIngestError")

    # Trying to catch transient as poison should fail
    with pytest.raises(TransientIngestError):
        try:
            raise transient
        except PoisonEpisodeError:
            pytest.fail("TransientIngestError should not be catchable as PoisonEpisodeError")


def test_module_docstring_states_default_to_transient_policy() -> None:
    """Module docstring documents the default-to-transient policy for unenumerated exceptions."""
    import fleet_memory.errors

    docstring = fleet_memory.errors.__doc__
    assert docstring is not None, "Module must have a docstring"

    # Check for key policy terms
    assert "transient" in docstring.lower(), "Docstring must mention transient handling"
    assert "unenumerated" in docstring.lower() or "unknown" in docstring.lower() or "unhandled" in docstring.lower(), \
        "Docstring must address unenumerated/unknown exceptions"


def test_poison_episode_error_can_be_raised_and_caught() -> None:
    """PoisonEpisodeError can be raised and caught correctly."""
    from fleet_memory.errors import PoisonEpisodeError

    with pytest.raises(PoisonEpisodeError) as exc_info:
        raise PoisonEpisodeError(reason="test failure")

    assert exc_info.value.reason == "test failure"


def test_transient_ingest_error_can_be_raised_and_caught() -> None:
    """TransientIngestError can be raised and caught correctly."""
    from fleet_memory.errors import TransientIngestError

    with pytest.raises(TransientIngestError) as exc_info:
        raise TransientIngestError("service down")

    assert "service down" in str(exc_info.value)
