"""Job-specific composition by complexity band for fleet-memory retrieval.

Adjusts the type mix and per-type budget share based on job complexity:
- SIMPLE: Favors documents, reduces patterns/warnings
- STANDARD: Balanced mix across all types
- COMPLEX: Favors patterns/warnings for comprehensive analysis

Composition shapes the input to assembly (which types, what share) but does not
bypass the tiktoken budget enforcement in TASK-RA-003.

Producer: TASK-RA-004
Consumer: FEAT-MEM-05 (search/assembly pipeline)
"""

from __future__ import annotations

from enum import Enum

from langgraph.store.base import SearchItem


class ComplexityBand(str, Enum):
    """Job complexity bands for context composition.

    Single source of truth for complexity band names (AC-4).
    """

    SIMPLE = "simple"
    STANDARD = "standard"
    COMPLEX = "complex"


# Type mix ratios for each complexity band
# Format: {band: {type_category: weight}}
# Higher weight = more items of this type included
_TYPE_MIX_WEIGHTS = {
    ComplexityBand.SIMPLE: {
        "pattern_warning": 0.3,  # Reduce patterns/warnings
        "other": 1.0,  # Favor documents and other types
    },
    ComplexityBand.STANDARD: {
        "pattern_warning": 1.0,  # Balanced mix
        "other": 1.0,
    },
    ComplexityBand.COMPLEX: {
        "pattern_warning": 2.0,  # Favor patterns/warnings
        "other": 0.6,  # Reduce other types
    },
}


def _extract_payload_type(natural_key: str) -> str | None:
    """Extract payload type from natural key format type:project:identifier.

    Args:
        natural_key: Natural key string (e.g., "document:proj_a:1")

    Returns:
        Payload type string or None if natural_key is malformed
    """
    parts = natural_key.split(":")
    if len(parts) >= 1:
        return parts[0]
    return None


def _is_pattern_or_warning(item: SearchItem) -> bool:
    """Check if item is a pattern or warning type.

    Args:
        item: SearchItem to check

    Returns:
        True if item is pattern or warning type, False otherwise
    """
    natural_key = item.value.get("natural_key", "")
    payload_type = _extract_payload_type(natural_key)
    return payload_type in ("pattern", "warning")


def _apply_weighted_composition(
    items: list[SearchItem], weights: dict[str, float]
) -> list[SearchItem]:
    """Compose items based on type category weights, adjusting both selection and order.

    Strategy: Select and interleave items from different type categories based on
    their weights. Higher weight types get more slots in the final composition.

    Args:
        items: List of SearchItem ordered by relevance (desc)
        weights: Type category weights {"pattern_warning": float, "other": float}

    Returns:
        Composed list with adjusted type mix and ordering
    """
    # Separate items by category (maintaining relevance order within each)
    pattern_warning_items = [item for item in items if _is_pattern_or_warning(item)]
    other_items = [item for item in items if not _is_pattern_or_warning(item)]

    # Get weights
    pw_weight = weights.get("pattern_warning", 1.0)
    other_weight = weights.get("other", 1.0)

    # Calculate how many items to take from each category
    # Strategy: distribute slots proportionally based on weights
    total_items = len(items)
    total_weight = pw_weight + other_weight

    if total_weight > 0:
        # Special case: if one category is empty, take all from the other
        if not pattern_warning_items:
            selected_pw = []
            selected_other = other_items
        elif not other_items:
            selected_pw = pattern_warning_items
            selected_other = []
        else:
            # Calculate proportional allocation with ceiling for rounding
            # Use max(1, ...) to ensure at least 1 item if category has any
            pw_target = total_items * (pw_weight / total_weight)
            other_target = total_items * (other_weight / total_weight)

            # Round to ensure we get reasonable distribution
            pw_slots = max(1, min(int(pw_target + 0.5), len(pattern_warning_items)))
            other_slots = max(1, min(int(other_target + 0.5), len(other_items)))

            # Take top items from each category based on slots
            selected_pw = pattern_warning_items[:pw_slots]
            selected_other = other_items[:other_slots]
    else:
        selected_pw = []
        selected_other = []

    # Interleave selected items based on relative weights
    result: list[SearchItem] = []
    pw_index = 0
    other_index = 0

    # Calculate ratios for interleaving
    pw_ratio = pw_weight / total_weight if total_weight > 0 else 0.5
    other_ratio = other_weight / total_weight if total_weight > 0 else 0.5

    # Interleave items based on ratios
    pw_balance = 0.0
    other_balance = 0.0

    while pw_index < len(selected_pw) or other_index < len(selected_other):
        # Add to balance counters
        pw_balance += pw_ratio
        other_balance += other_ratio

        # Take from the category with highest balance
        if pw_balance >= other_balance:
            if pw_index < len(selected_pw):
                result.append(selected_pw[pw_index])
                pw_index += 1
                pw_balance -= 1.0
            elif other_index < len(selected_other):
                # Fallback if pw exhausted
                result.append(selected_other[other_index])
                other_index += 1
                other_balance -= 1.0
        else:
            if other_index < len(selected_other):
                result.append(selected_other[other_index])
                other_index += 1
                other_balance -= 1.0
            elif pw_index < len(selected_pw):
                # Fallback if other exhausted
                result.append(selected_pw[pw_index])
                pw_index += 1
                pw_balance -= 1.0

    return result


def compose_by_complexity(
    ranked_results: list[SearchItem],
    complexity_band: ComplexityBand | str,
) -> list[SearchItem]:
    """Compose search results by complexity band, adjusting type mix.

    Takes ranked search results and reorders them based on the job's complexity band.
    This adjusts which types (patterns/warnings vs documents) get prioritized when
    the assembly function applies the token budget.

    - SIMPLE: Reduces patterns/warnings, favors documents
    - STANDARD: Balanced mix across all types
    - COMPLEX: Increases patterns/warnings for comprehensive analysis

    The composition does NOT bypass assembly's token budget enforcement - it only
    shapes the input ordering so assembly naturally includes more of certain types.

    Args:
        ranked_results: List of SearchItem ordered by relevance (desc)
        complexity_band: Complexity band (SIMPLE, STANDARD, or COMPLEX)

    Returns:
        Reordered list with adjusted type mix (still ranked by effective priority)

    Example:
        >>> results = await search(request, store)
        >>> composed = compose_by_complexity(results, ComplexityBand.COMPLEX)
        >>> assembly = assemble_context(composed, token_budget=2000)
        >>> # assembly.contributing_types will have more patterns/warnings
    """
    # Handle empty results
    if not ranked_results:
        return []

    # Normalize complexity_band to enum
    if isinstance(complexity_band, str):
        complexity_band = ComplexityBand(complexity_band)

    # Get type mix weights for this complexity band
    weights = _TYPE_MIX_WEIGHTS[complexity_band]

    # Apply weighted composition
    return _apply_weighted_composition(ranked_results, weights)
