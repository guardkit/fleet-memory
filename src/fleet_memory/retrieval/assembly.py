"""Token-budgeted context assembly for fleet-memory retrieval.

Assembles ranked search results into a single context block that never exceeds
the token budget. Token measurement uses tiktoken cl100k_base encoding for
exact boundary compliance.

Producer: TASK-RA-003
Consumer: FEAT-MEM-05 (harness, downstream tasks)
"""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken
from langgraph.store.base import SearchItem

# Tiktoken encoding for token measurement (cl100k_base for GPT-4/GPT-3.5-turbo)
ENCODING_NAME = "cl100k_base"


@dataclass
class AssemblyResult:
    """Result of token-budgeted context assembly.

    Attributes:
        context_block: Assembled context string (never exceeds token budget)
        coverage_score: Fraction of budget filled (0.0-1.0)
        contributing_types: Set of payload types that contributed content
        tokens_used: Actual tokens consumed by the assembled block
    """

    context_block: str
    coverage_score: float
    contributing_types: set[str]
    tokens_used: int


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


def _measure_tokens(text: str, encoding: tiktoken.Encoding) -> int:
    """Measure token count of text using tiktoken encoding.

    Args:
        text: Text to measure
        encoding: tiktoken Encoding instance

    Returns:
        Number of tokens in text
    """
    return len(encoding.encode(text))


def assemble_context(
    ranked_results: list[SearchItem],
    token_budget: int,
) -> AssemblyResult:
    """Assemble ranked memories into a token-budgeted context block.

    Takes ranked search results (ordered by relevance descending) and assembles
    them into a single context block that never exceeds the token budget.
    Memories are added in order of relevance; when the budget is exhausted,
    remaining (lower-ranked) memories are omitted.

    Token measurement is performed on the **assembled block** using tiktoken
    cl100k_base encoding, not by summing per-memory estimates. This ensures
    exact boundary compliance.

    Args:
        ranked_results: List of SearchItem ordered by relevance (desc)
        token_budget: Maximum tokens allowed in assembled block

    Returns:
        AssemblyResult with context block, coverage score, and metadata

    Example:
        >>> results = await search(request, store)
        >>> assembly = assemble_context(results, token_budget=2000)
        >>> print(f"Coverage: {assembly.coverage_score:.0%}")
        >>> print(assembly.context_block)
    """
    # Handle zero budget
    if token_budget == 0:
        return AssemblyResult(
            context_block="",
            coverage_score=0.0,
            contributing_types=set(),
            tokens_used=0,
        )

    # Handle empty results
    if not ranked_results:
        return AssemblyResult(
            context_block="",
            coverage_score=0.0,
            contributing_types=set(),
            tokens_used=0,
        )

    # Get tiktoken encoding
    encoding = tiktoken.get_encoding(ENCODING_NAME)

    # Build context block incrementally, measuring after each addition
    included_items: list[SearchItem] = []
    current_block = ""

    for item in ranked_results:
        content = item.value.get("content", "")
        if not content:
            continue

        # Build candidate block with this item
        # Format: each memory on a new line with separator
        if current_block:
            candidate_block = current_block + "\n\n" + content
        else:
            candidate_block = content

        # Measure actual token count of assembled block
        candidate_tokens = _measure_tokens(candidate_block, encoding)

        # Check if candidate fits within budget
        if candidate_tokens <= token_budget:
            # Fits! Accept this item
            current_block = candidate_block
            included_items.append(item)
        else:
            # Over budget — SKIP this item and keep trying lower-ranked ones that
            # may still fit (greedy packing). Previously this was `break`, which
            # let a single oversized top-ranked chunk zero the entire context
            # block (see docs/evals/FEAT-MEM-05-parity-eval-2026-06-27.md).
            continue

    # Calculate final metrics
    tokens_used = _measure_tokens(current_block, encoding) if current_block else 0

    # Calculate coverage score
    if token_budget > 0:
        coverage_score = tokens_used / token_budget
    else:
        coverage_score = 0.0

    # Extract contributing payload types
    contributing_types: set[str] = set()
    for item in included_items:
        natural_key = item.value.get("natural_key", "")
        payload_type = _extract_payload_type(natural_key)
        if payload_type:
            contributing_types.add(payload_type)

    return AssemblyResult(
        context_block=current_block,
        coverage_score=coverage_score,
        contributing_types=contributing_types,
        tokens_used=tokens_used,
    )
