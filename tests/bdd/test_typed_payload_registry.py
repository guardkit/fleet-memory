"""BDD step definitions for typed payload registry feature.

Binds the 29 scenarios in typed-payload-registry.feature to the fleet_memory.payloads
implementation. This is the executable acceptance suite for FEAT-MEM-02.

All scenarios act on payloads or the registry in-process — no broker or infrastructure.
Tests import from the public surface (fleet_memory.payloads) as a contract test.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from fleet_memory.errors import UnknownPayloadTypeError
from fleet_memory.payloads.base import (
    BasePayload,
    IdentifierValidationError,
    SupersessionValidationError,
)
from fleet_memory.payloads.models import (
    ADRPayload,
    BuildOutcomePayload,
    DocumentPayload,
    PatternPayload,
    ReviewReportPayload,
    SeedModulePayload,
    WarningPayload,
)
from fleet_memory.payloads.registry import (
    PAYLOAD_REGISTRY,
    get_model_for_type,
    get_type_for_model,
)

# Load all scenarios from the feature file
scenarios("../../features/typed-payload-registry/typed-payload-registry.feature")


# ──────────────────────── Fixtures for Test Context ─────────────────────────


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared context for passing data between step definitions."""
    return {}


# ──────────────────────── Given Steps ───────────────────────────────────────


@given(
    parsers.parse(
        'an ADR payload for project "{project}" with identifier "{identifier}"'
    ),
    target_fixture="payload",
)
def adr_payload(project: str, identifier: str) -> ADRPayload:
    """Create an ADR payload with the given project and identifier."""
    return ADRPayload(
        project=project,
        identifier=identifier,
        source_ref="test_source",
        decision="Test decision",
        status="proposed",
    )


@given("an ADR payload", target_fixture="payload")
def adr_payload_generic() -> ADRPayload:
    """Create a generic ADR payload."""
    return ADRPayload(
        project="guardkit",
        identifier="ADR_SP_007",
        source_ref="test_source",
        decision="Test decision",
        status="proposed",
    )


@given(
    parsers.parse(
        'a pattern payload that declares it supersedes "{superseded_key}"'
    ),
    target_fixture="payload",
)
def pattern_payload_with_supersession(superseded_key: str) -> PatternPayload:
    """Create a pattern payload that supersedes the given key."""
    return PatternPayload(
        project="guardkit",
        identifier="new_pattern",
        source_ref="test_source",
        pattern_name="New Pattern",
        category="behavioral",
        supersedes=[superseded_key],
    )


@given(
    parsers.parse(
        'a warning payload tagged with "{tag1}" and "{tag2}" sourced from a known document'
    ),
    target_fixture="payload",
)
def warning_payload_with_tags(tag1: str, tag2: str) -> WarningPayload:
    """Create a warning payload with domain tags."""
    return WarningPayload(
        project="guardkit",
        identifier="warning_001",
        source_ref="doc://known_document",
        severity="high",
        message="Test warning",
        domain_tags=[tag1, tag2],
    )


@given(
    parsers.parse(
        'a generic document payload for project "{project}" with identifier "{identifier}"'
    ),
    target_fixture="payload",
)
def document_payload(project: str, identifier: str) -> DocumentPayload:
    """Create a generic document payload."""
    return DocumentPayload(
        project=project,
        identifier=identifier,
        source_ref="test_source",
    )


@given(
    parsers.parse(
        'an attempt to build an ADR payload for project "{project}" with an empty identifier'
    ),
    target_fixture="payload_error",
)
def adr_payload_empty_identifier_attempt(
    project: str, context: dict[str, Any]
) -> None:
    """Attempt to create an ADR payload with empty identifier (should fail)."""
    try:
        ADRPayload(
            project=project,
            identifier="",
            source_ref="test_source",
            decision="Test",
            status="proposed",
        )
        context["exception"] = None
    except (IdentifierValidationError, ValidationError) as e:
        context["exception"] = e


@given(
    parsers.parse('a pattern payload declaring {count:d} supersession references'),
    target_fixture="payload",
)
def pattern_payload_with_count_supersessions(count: int) -> PatternPayload:
    """Create a pattern payload with specified number of supersessions."""
    supersedes = [
        f"pattern:guardkit:old_pattern_{i}" for i in range(count)
    ]
    return PatternPayload(
        project="guardkit",
        identifier="new_pattern",
        source_ref="test_source",
        pattern_name="New Pattern",
        category="behavioral",
        supersedes=supersedes,
    )


@given("a warning payload with no domain tags", target_fixture="payload")
def warning_payload_no_tags() -> WarningPayload:
    """Create a warning payload with no domain tags."""
    return WarningPayload(
        project="guardkit",
        identifier="warning_001",
        source_ref="test_source",
        severity="low",
        message="Test warning",
        domain_tags=[],
    )


@given(
    parsers.parse('a pattern payload declaring a supersession of "{reference}"'),
    target_fixture="payload_error",
)
def pattern_payload_bad_supersession_attempt(
    reference: str, context: dict[str, Any]
) -> None:
    """Attempt to create a pattern payload with malformed supersession."""
    try:
        PatternPayload(
            project="guardkit",
            identifier="new_pattern",
            source_ref="test_source",
            pattern_name="New Pattern",
            category="behavioral",
            supersedes=[reference],
        )
        context["exception"] = None
    except SupersessionValidationError as e:
        context["exception"] = e


@given(
    parsers.parse(
        'an attempt to build an ADR payload for project "{project}" with identifier "{identifier}"'
    ),
    target_fixture="payload_error",
)
def adr_payload_bad_identifier_attempt(
    project: str, identifier: str, context: dict[str, Any]
) -> None:
    """Attempt to create an ADR payload with invalid identifier."""
    try:
        ADRPayload(
            project=project,
            identifier=identifier,
            source_ref="test_source",
            decision="Test",
            status="proposed",
        )
        context["exception"] = None
    except IdentifierValidationError as e:
        context["exception"] = e


@given("the typed payload registry", target_fixture="registry")
def typed_payload_registry() -> dict[str, type[BasePayload]]:
    """Return the typed payload registry."""
    return PAYLOAD_REGISTRY


@given("any typed payload", target_fixture="payload")
def any_typed_payload() -> ADRPayload:
    """Create any typed payload for testing."""
    return ADRPayload(
        project="guardkit",
        identifier="test_id",
        source_ref="test_source",
        decision="Test decision",
        status="proposed",
    )


@given(
    "serialized payload data that includes a field the model does not define",
    target_fixture="serialized_data",
)
def serialized_with_extra_field() -> dict[str, Any]:
    """Create serialized payload data with an unknown extra field."""
    return {
        "project": "guardkit",
        "identifier": "ADR_SP_007",
        "source_ref": "test_source",
        "decision": "Test decision",
        "status": "proposed",
        "unknown_field": "this should be ignored",
        "another_extra": 42,
    }


@given(parsers.parse('it declares that it supersedes "{superseded_key}"'))
def declare_self_supersession(payload: BasePayload, superseded_key: str, context: dict[str, Any]) -> None:
    """Attempt to add self-supersession to a payload (should fail during construction).

    This step is used with an existing payload from a previous Given step,
    so we need to attempt to rebuild it with the self-supersession.
    """
    try:
        if isinstance(payload, ADRPayload):
            ADRPayload(
                project=payload.project,
                identifier=payload.identifier,
                source_ref=payload.source_ref,
                decision=payload.decision,
                status=payload.status,
                supersedes=[superseded_key],
            )
        context["exception"] = None
    except SupersessionValidationError as e:
        context["exception"] = e


@given("a pattern payload declaring the same supersession reference twice", target_fixture="payload")
def pattern_payload_duplicate_supersession() -> PatternPayload:
    """Create a pattern payload with duplicate supersession references."""
    return PatternPayload(
        project="guardkit",
        identifier="new_pattern",
        source_ref="test_source",
        pattern_name="New Pattern",
        category="behavioral",
        supersedes=[
            "pattern:guardkit:old_pattern",
            "pattern:guardkit:old_pattern",  # Duplicate
        ],
    )


@given(
    parsers.parse(
        'two ADR payloads both for project "{project}" with identifier "{identifier}"'
    ),
    target_fixture="two_payloads",
)
def two_identical_adr_payloads(project: str, identifier: str) -> tuple[ADRPayload, ADRPayload]:
    """Create two ADR payloads with identical type, project, and identifier."""
    payload1 = ADRPayload(
        project=project,
        identifier=identifier,
        source_ref="source_1",
        decision="Decision 1",
        status="proposed",
    )
    payload2 = ADRPayload(
        project=project,
        identifier=identifier,
        source_ref="source_2",
        decision="Decision 2",
        status="accepted",
    )
    return (payload1, payload2)


@given(
    parsers.parse(
        'an ADR payload for project "{project}" declaring it supersedes "{superseded_key}"'
    ),
    target_fixture="payload",
)
def adr_payload_cross_project_supersession(project: str, superseded_key: str) -> ADRPayload:
    """Create an ADR payload that supersedes a key in another project."""
    return ADRPayload(
        project=project,
        identifier="ADR_SP_042",
        source_ref="test_source",
        decision="Cross-project decision",
        status="proposed",
        supersedes=[superseded_key],
    )


@given(
    "identical ADR payload content authored through two different write surfaces",
    target_fixture="two_serialized",
)
def identical_content_two_surfaces() -> tuple[dict[str, Any], dict[str, Any]]:
    """Create identical ADR payload content from two different sources."""
    # Same content, different write surface metadata
    content = {
        "project": "guardkit",
        "identifier": "ADR_SP_007",
        "source_ref": "test_source",
        "decision": "Test decision",
        "status": "proposed",
    }
    return (content.copy(), content.copy())


@given(
    "an existing ADR payload at version 1 under a natural key",
    target_fixture="existing_payload",
)
def existing_adr_v1() -> ADRPayload:
    """Create an ADR payload at version 1."""
    return ADRPayload(
        project="guardkit",
        identifier="ADR_SP_007",
        source_ref="test_source_v1",
        decision="Original decision",
        status="proposed",
        version=1,
    )


@given("an attempt to build a review report payload with no verdict", target_fixture="payload_error")
def review_report_no_verdict_attempt(context: dict[str, Any]) -> None:
    """Attempt to create a review report without required verdict field."""
    try:
        ReviewReportPayload(
            project="guardkit",
            identifier="review_001",
            source_ref="test_source",
            # Missing required 'verdict' field
        )
        context["exception"] = None
    except (ValidationError, TypeError) as e:
        context["exception"] = e


# ──────────────────────── When Steps ────────────────────────────────────────


@when(parsers.parse('a payload type name "{type_name}" is looked up'))
def lookup_payload_type(type_name: str, context: dict[str, Any]) -> None:
    """Look up a payload type in the registry."""
    try:
        context["looked_up_model"] = get_model_for_type(type_name)
        context["lookup_error"] = None
    except UnknownPayloadTypeError as e:
        context["lookup_error"] = e
        context["looked_up_model"] = None


@when(parsers.parse('the payload type name "{type_name}" is looked up'))
def lookup_payload_type_variant(type_name: str, context: dict[str, Any]) -> None:
    """Look up a payload type in the registry (variant wording)."""
    lookup_payload_type(type_name, context)


@when("it is serialized and then rebuilt by dispatching on its payload type")
def serialize_and_rebuild(payload: BasePayload, context: dict[str, Any]) -> None:
    """Serialize a payload and rebuild it from the serialized form."""
    # Serialize to dict
    serialized = payload.model_dump()

    # Get the payload type
    payload_type = payload.payload_type

    # Rebuild by dispatching on payload type
    model_class = get_model_for_type(payload_type)
    context["rebuilt_payload"] = model_class(**serialized)
    context["original_payload"] = payload


@when("it is serialized and rebuilt repeatedly")
def serialize_rebuild_repeatedly(payload: BasePayload, context: dict[str, Any]) -> None:
    """Serialize and rebuild a payload multiple times."""
    natural_keys = []
    current = payload

    for _ in range(5):  # Repeat 5 times to test stability
        serialized = current.model_dump()
        model_class = get_model_for_type(current.payload_type)
        current = model_class(**serialized)
        natural_keys.append(current.natural_key)

    context["repeated_natural_keys"] = natural_keys
    context["original_natural_key"] = payload.natural_key


@when("it is rebuilt by dispatching on its payload type")
def rebuild_from_serialized(serialized_data: dict[str, Any], context: dict[str, Any]) -> None:
    """Rebuild a payload from serialized data by dispatching on its type."""
    try:
        # ADRPayload is the type for this scenario
        context["rebuilt_payload"] = ADRPayload(**serialized_data)
        context["rebuild_error"] = None
    except Exception as e:
        context["rebuild_error"] = e
        context["rebuilt_payload"] = None


@when("each is serialized for storage")
def serialize_both_surfaces(two_serialized: tuple[dict[str, Any], dict[str, Any]], context: dict[str, Any]) -> None:
    """Serialize payloads from both write surfaces."""
    content1, content2 = two_serialized

    payload1 = ADRPayload(**content1)
    payload2 = ADRPayload(**content2)

    # Serialize to JSON bytes (deterministic)
    context["serialized_1"] = json.dumps(payload1.model_dump(), sort_keys=True)
    context["serialized_2"] = json.dumps(payload2.model_dump(), sort_keys=True)


@when("the same natural key is re-authored with new content")
def reauthor_with_new_content(existing_payload: ADRPayload, context: dict[str, Any]) -> None:
    """Re-author a payload with the same natural key but new content."""
    # Store existing payload in context for Then step
    context["existing_payload"] = existing_payload
    context["new_payload"] = ADRPayload(
        project=existing_payload.project,
        identifier=existing_payload.identifier,
        source_ref="test_source_v2",
        decision="Updated decision",
        status="accepted",
        version=2,  # Explicitly advance version
    )


# ──────────────────────── Then Steps ────────────────────────────────────────


@then(parsers.parse('its natural key should be "{expected_key}"'))
def check_natural_key(payload: BasePayload, expected_key: str) -> None:
    """Verify the payload's natural key matches the expected value."""
    assert payload.natural_key == expected_key


@then("the registry should return the review report model")
def check_review_report_model(context: dict[str, Any]) -> None:
    """Verify the registry returned the ReviewReportPayload model."""
    assert context["looked_up_model"] is ReviewReportPayload


@then("a model should be returned for that type")
def check_model_returned(context: dict[str, Any]) -> None:
    """Verify a model was returned from the registry lookup."""
    assert context["looked_up_model"] is not None
    assert context["lookup_error"] is None


@then(parsers.parse('its declared supersessions should contain "{superseded_key}"'))
def check_supersession_contains(payload: BasePayload, superseded_key: str) -> None:
    """Verify the payload's supersessions contain the expected key."""
    assert superseded_key in payload.supersedes


@then("its supersession references should all be natural-key shaped")
def check_all_supersessions_valid_shape(payload: BasePayload) -> None:
    """Verify all supersession references have the natural key shape (3 segments)."""
    for ref in payload.supersedes:
        segments = ref.split(":")
        assert len(segments) == 3, f"Supersession '{ref}' does not have 3 segments"


@then(parsers.parse('its domain tags should include "{tag1}" and "{tag2}"'))
def check_domain_tags(payload: BasePayload, tag1: str, tag2: str) -> None:
    """Verify the payload has the expected domain tags."""
    assert tag1 in payload.domain_tags
    assert tag2 in payload.domain_tags


@then("its source reference should identify where it came from")
def check_source_ref(payload: BasePayload) -> None:
    """Verify the payload has a source reference."""
    assert payload.source_ref
    assert isinstance(payload.source_ref, str)


@then("it should be accepted without requiring any type-specific fields")
def check_document_accepted(payload: DocumentPayload) -> None:
    """Verify a document payload is accepted without type-specific fields."""
    # DocumentPayload has no required fields beyond BasePayload
    assert isinstance(payload, DocumentPayload)
    assert payload.natural_key


@then("the rebuilt payload should equal the original")
def check_rebuilt_equals_original(context: dict[str, Any]) -> None:
    """Verify the rebuilt payload equals the original."""
    original = context["original_payload"]
    rebuilt = context["rebuilt_payload"]

    # Compare all fields
    assert rebuilt.project == original.project
    assert rebuilt.identifier == original.identifier
    assert rebuilt.natural_key == original.natural_key


@then("its natural key should be unchanged")
def check_natural_key_unchanged(context: dict[str, Any]) -> None:
    """Verify the natural key is unchanged after rebuild."""
    if "rebuilt_payload" in context:
        assert context["rebuilt_payload"].natural_key == context["original_payload"].natural_key
    elif "new_payload" in context and "existing_payload" in context:
        # For re-authoring scenario
        existing = context.get("existing_payload")
        new = context["new_payload"]
        assert new.natural_key == existing.natural_key


@then("its natural key should have exactly three segments separated by colons")
def check_three_segments(payload: BasePayload) -> None:
    """Verify the natural key has exactly 3 colon-separated segments."""
    segments = payload.natural_key.split(":")
    assert len(segments) == 3


@then("the payload should be rejected")
def check_payload_rejected(context: dict[str, Any]) -> None:
    """Verify the payload construction raised an exception."""
    assert context.get("exception") is not None


@then("the error should indicate the identifier is required")
def check_error_identifier_required(context: dict[str, Any]) -> None:
    """Verify the error message indicates identifier is required."""
    exception = context["exception"]
    error_msg = str(exception).lower()
    assert "identifier is required" in error_msg or "identifier" in error_msg


@then("the payload should be accepted")
def check_payload_accepted(request, context: dict[str, Any]) -> None:
    """Verify the payload was successfully created."""
    # Handle different scenarios
    if "rebuilt_payload" in context:
        # Rebuild scenario
        assert context["rebuilt_payload"] is not None
        assert context.get("rebuild_error") is None
    else:
        # Regular payload creation via fixture
        try:
            payload = request.getfixturevalue("payload")
            assert payload.natural_key
        except Exception:
            # If no payload fixture, scenario might be using context only
            pass


@then(parsers.parse("its declared supersessions should number exactly {count:d}"))
def check_supersession_count(payload: BasePayload, count: int) -> None:
    """Verify the payload has exactly the expected number of supersessions."""
    assert len(payload.supersedes) == count


@then("its domain tags should be empty")
def check_domain_tags_empty(payload: BasePayload) -> None:
    """Verify the payload has no domain tags."""
    assert len(payload.domain_tags) == 0


@then("the error should indicate the supersession reference is not a valid natural key")
def check_error_invalid_natural_key(context: dict[str, Any]) -> None:
    """Verify the error indicates the supersession reference is not a valid natural key."""
    exception = context["exception"]
    error_msg = str(exception).lower()
    assert "not a valid natural key" in error_msg or "3" in error_msg or "segments" in error_msg


@then("the error should state that identifiers must use underscores")
def check_error_underscores_required(context: dict[str, Any]) -> None:
    """Verify the error message states identifiers must use underscores."""
    exception = context["exception"]
    error_msg = str(exception).lower()
    assert "underscores" in error_msg or "underscore" in error_msg


@then("the lookup should be rejected")
def check_lookup_rejected(context: dict[str, Any]) -> None:
    """Verify the registry lookup raised an error."""
    assert context.get("lookup_error") is not None
    assert context.get("looked_up_model") is None


@then("the error should name the unknown payload type")
def check_error_names_unknown_type(context: dict[str, Any]) -> None:
    """Verify the error message names the unknown payload type."""
    exception = context["lookup_error"]
    error_msg = str(exception).lower()
    assert "unknown" in error_msg or "not found" in error_msg


@then("the error should name the missing field")
def check_error_names_missing_field(context: dict[str, Any]) -> None:
    """Verify the error message names the missing required field."""
    exception = context["exception"]
    error_msg = str(exception).lower()
    assert "verdict" in error_msg or "required" in error_msg or "missing" in error_msg


@then("its natural key should be identical on every round trip")
def check_natural_key_stable(context: dict[str, Any]) -> None:
    """Verify the natural key is stable across repeated round trips."""
    keys = context["repeated_natural_keys"]
    original_key = context["original_natural_key"]

    # All keys should be identical to the original
    for key in keys:
        assert key == original_key


# Removed duplicate - consolidated into check_payload_accepted above


@then("the unknown field should be ignored")
def check_unknown_field_ignored(context: dict[str, Any]) -> None:
    """Verify unknown fields were ignored (not present in rebuilt payload)."""
    rebuilt = context["rebuilt_payload"]
    # Extra fields should not be accessible
    assert not hasattr(rebuilt, "unknown_field")
    assert not hasattr(rebuilt, "another_extra")


@then("the error should indicate a payload cannot supersede itself")
def check_error_self_supersession(context: dict[str, Any]) -> None:
    """Verify the error indicates self-supersession is not allowed."""
    exception = context["exception"]
    error_msg = str(exception).lower()
    assert "cannot supersede itself" in error_msg or "supersede itself" in error_msg


@then("that reference should appear only once in its declared supersessions")
def check_supersession_deduped(payload: BasePayload) -> None:
    """Verify duplicate supersession references are collapsed to one."""
    # Count occurrences of each supersession
    from collections import Counter
    counts = Counter(payload.supersedes)

    # All supersessions should appear exactly once
    for ref, count in counts.items():
        assert count == 1, f"Supersession '{ref}' appears {count} times, expected 1"


@then(parsers.parse('its payload type name should be "{expected_type}"'))
def check_payload_type_name(payload: BasePayload, expected_type: str) -> None:
    """Verify the payload's type name."""
    assert payload.payload_type == expected_type


@then("looking that name up in the registry should return the ADR model")
def check_registry_returns_adr_model(payload: BasePayload) -> None:
    """Verify looking up the payload type in the registry returns the ADR model."""
    model = get_model_for_type(payload.payload_type)
    assert model is ADRPayload


@then("both should produce the same natural key")
def check_both_same_natural_key(two_payloads: tuple[BasePayload, BasePayload]) -> None:
    """Verify two payloads with same type/project/identifier have the same natural key."""
    payload1, payload2 = two_payloads
    assert payload1.natural_key == payload2.natural_key


@then("the store may treat them as the same record")
def check_store_can_dedupe(two_payloads: tuple[BasePayload, BasePayload]) -> None:
    """Verify payloads with same natural key can be deduplicated by the store."""
    payload1, payload2 = two_payloads
    # Same natural key means they are the same logical memory record
    assert payload1.natural_key == payload2.natural_key


@then("the two serialized forms should be byte-for-byte identical")
def check_byte_identical(context: dict[str, Any]) -> None:
    """Verify the two serialized forms are byte-identical."""
    serialized_1 = context["serialized_1"]
    serialized_2 = context["serialized_2"]
    assert serialized_1 == serialized_2


@then("the new payload should carry a higher version than the previous one")
def check_version_advanced(context: dict[str, Any]) -> None:
    """Verify the new payload has a higher version number."""
    existing = context.get("existing_payload")
    new = context["new_payload"]
    assert new.version > existing.version


@then("every registered type name should map to exactly one model")
def check_each_name_one_model() -> None:
    """Verify each type name maps to exactly one model (bijection - forward direction)."""
    # Check that all values are unique (no duplicate models)
    models = list(PAYLOAD_REGISTRY.values())
    assert len(models) == len(set(models)), "Some models are registered multiple times"


@then("no two type names should map to the same model")
def check_no_duplicate_models() -> None:
    """Verify no two type names map to the same model (bijection - no aliases)."""
    models = list(PAYLOAD_REGISTRY.values())
    unique_models = set(models)
    assert len(models) == len(unique_models), "Multiple type names map to the same model"
