"""Identifier normalization for backward-edge episode types (schema contract §2.3).

The backward-edge episode contract builds each payload's natural-key ``identifier``
segment from raw source ids (correlation_id, gate_id, suite_id, run id, ...). Those raw
ids carry hyphens and other characters the identifier charset forbids
(``^[a-zA-Z0-9_]+$``), so producers MUST normalize deterministically — a retried publish
has to land on the same natural key for the writer's content-hash no-op to hold.

This module is the single canonical implementation of the §2.3 NORM rules so producers
(forge, fleet-evals), the seed scripts, and the Chronicler never drift:

- ``norm``            — replace every char outside ``[a-zA-Z0-9_]`` with ``_``.
- ``norm_project``    — NORM plus lowercase (the search side requires ``^[a-z0-9_]+$``;
                        a cased project is stored but unreachable, §2.3).
- ``composite_hash``  — the ``hex12(SHA-256 over raw parts joined with 0x1F)``
                        disambiguator; NORM's ``_`` is also its joiner, so naive
                        concatenation of composite ids is non-injective (§2.3
                        injectivity warning). The 0x1F unit separator cannot appear in
                        the raw ids, so the join is unambiguous.
- ``composite_identifier`` — the §4.5 shape ``NORM(primary) + "_" + hex12(...)``;
                        the primary stays human-greppable, the hash disambiguates.

Raw ids are carried UNMODIFIED in each payload's own fields (§2.3); only the natural-key
segment is normalized here.
"""

from __future__ import annotations

import hashlib
import re

# Everything outside the identifier charset (^[a-zA-Z0-9_]+$) collapses to the joiner.
_NON_IDENTIFIER = re.compile(r"[^a-zA-Z0-9_]")

# 0x1F (ASCII unit separator): a control char that cannot occur in a source id, so
# joining raw parts with it makes composite hashing injective over the part boundaries.
_UNIT_SEPARATOR = "\x1f"


def norm(source_id: str) -> str:
    """Normalize a raw source id to the identifier charset (§2.3 NORM).

    Replaces every character outside ``[a-zA-Z0-9_]`` with ``_``. Case is preserved
    (the ``ADR_SP_007`` precedent); use :func:`norm_project` for the project segment,
    which additionally lowercases.

    Args:
        source_id: The raw source id (correlation_id, gate_id, run id, ...).

    Returns:
        The normalized identifier segment.
    """
    return _NON_IDENTIFIER.sub("_", source_id)


def norm_project(project_id: str) -> str:
    """Normalize a project id: NORM then lowercase (§2.3).

    The search side requires ``^[a-z0-9_]+$``; a cased project is stored but unreachable
    through ``SearchRequest``, so the project segment is lowercased in addition to NORM.

    Args:
        project_id: The raw target-repo project id.

    Returns:
        The normalized, lowercased project segment.
    """
    return norm(project_id).lower()


def composite_hash(*raw_parts: str) -> str:
    """Disambiguating hash for composite identifiers (§2.3 composite rule).

    Returns ``hex12(SHA-256 over the raw parts joined with 0x1F)``. Because NORM's
    replacement character ``_`` is also the natural joiner, composite identifiers built
    by naive concatenation are non-injective (``("po-heldout", "idea-x")`` and
    ``("po-heldout-idea", "x")`` would collide); the 0x1F-separated hash disambiguates.

    Args:
        *raw_parts: The raw (un-normalized) source ids that compose the identifier.

    Returns:
        A 12-character lowercase hex digest.
    """
    raw = _UNIT_SEPARATOR.join(raw_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def composite_identifier(primary_id: str, *raw_parts: str) -> str:
    """Build a composite natural-key identifier (§2.3 / §4.5 shape).

    Produces ``NORM(primary_id) + "_" + composite_hash(primary_id, *raw_parts)`` — the
    primary keeps rows human-greppable while the hash guarantees injectivity across the
    combined source ids. Used by ``grading_outcome`` (``suite_id`` ⟂ ``checkpoint_id``);
    ``approval_decision`` composes its own cycle-infixed shape from :func:`norm` and
    :func:`composite_hash` directly (§4.2).

    Args:
        primary_id: The primary raw id (kept human-greppable in the output).
        *raw_parts: Additional raw ids folded into the disambiguating hash.

    Returns:
        The composite identifier segment.
    """
    return f"{norm(primary_id)}_{composite_hash(primary_id, *raw_parts)}"
