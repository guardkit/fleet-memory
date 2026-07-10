"""Role-scoped retrieval defaults — D-WS4-6 read side (schema contract §6).

D-WS4-6 (DECIDED 2026-07-07, ACCEPTED) makes role a ``domain_tag`` taxonomy with two
enacted mechanisms:

- **write side** — a required ``role:<seat>`` tag on role-attributable payloads
  (``payloads/backward_edge.py``: ``RoleAttributedPayload``);
- **read side** — *scoped-default-on-read*: a role's harness passes its own ``role:`` tag
  by default (and a per-role ``token_budget`` + ``payload_types`` allowlist) and must
  explicitly opt out to read cross-role.

This module is that read-side **config seat**. The MECHANISM is the deliverable and lands
now; the budget VALUES and allowlists are **placeholders until ABL-006 reports** (WS4
§6.4 gate — no retrieval-side tuning before it). Do not treat the numbers below as tuned.

Forward-compatibility with §5 landing gating: a role's default ``payload_types`` allowlist
may name types whose producer is not yet wired (so not yet in ``PAYLOAD_REGISTRY``).
:func:`role_scoped_search_request` intersects the allowlist with the live registry before
building a ``SearchRequest`` (which rejects unknown types), so a gated type becomes
reachable automatically the moment it registers — no config change needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fleet_memory.payloads.registry import PAYLOAD_REGISTRY
from fleet_memory.retrieval.search_request import SearchRequest

# The budget values and allowlists below are ABL-006-gated placeholders (WS4 §6.4), not
# tuned parameters. The seat exists so harnesses have somewhere to read a default from.
BUDGETS_ARE_PLACEHOLDER = True

# The D-WS4-6 role taxonomy (§6): one seat per §5-table producer, additive as seats appear.
ROLE_PRODUCT_OWNER = "product-owner"
ROLE_ARCHITECT = "architect"
ROLE_COACH = "coach"
ROLE_QA_VERIFIER = "qa-verifier"
ROLE_PLAYER = "player"


@dataclass(frozen=True)
class RoleRetrievalDefault:
    """A role's default retrieval envelope (config seat; values ABL-006-gated).

    Attributes:
        token_budget: Default retrieval token budget for the seat.
        payload_types: Default payload-type allowlist. Empty means UNRESTRICTED
            ("all registered types" — the Player default). Names of not-yet-registered
            types are allowed here and filtered at request-build time.
    """

    token_budget: int
    payload_types: tuple[str, ...] = field(default_factory=tuple)


# Illustrative seat defaults (§6). VALUES ARE PLACEHOLDERS until ABL-006 (WS4 §6.4). The
# allowlists intentionally name producer-gated types (planning_outcome, spec_survival,
# live_verdict) so they become reachable the moment those register — see module docstring.
ROLE_RETRIEVAL_DEFAULTS: dict[str, RoleRetrievalDefault] = {
    ROLE_PRODUCT_OWNER: RoleRetrievalDefault(
        token_budget=4000,
        payload_types=("adr", "planning_outcome", "spec_survival", "document"),
    ),
    ROLE_ARCHITECT: RoleRetrievalDefault(
        token_budget=4000,
        payload_types=("adr", "pattern", "build_outcome"),
    ),
    ROLE_COACH: RoleRetrievalDefault(
        token_budget=2500,
        payload_types=("build_outcome", "review_report", "warning"),
    ),
    ROLE_QA_VERIFIER: RoleRetrievalDefault(
        token_budget=1500,
        payload_types=("live_verdict", "build_outcome"),
    ),
    # Player: unrestricted payload types (empty allowlist == all registered types).
    ROLE_PLAYER: RoleRetrievalDefault(token_budget=6000, payload_types=()),
}


def role_tag(role: str) -> str:
    """Return the ``role:<seat>`` domain-tag facet for a seat (D-WS4-6 taxonomy)."""
    return f"role:{role}"


def _registered(payload_types: tuple[str, ...]) -> list[str]:
    """Keep only currently-registered types (SearchRequest rejects unknown ones)."""
    return [pt for pt in payload_types if pt in PAYLOAD_REGISTRY]


def role_scoped_search_request(
    role: str,
    project: str,
    *,
    query: str | None = None,
    token_budget: int | None = None,
    payload_types: list[str] | None = None,
    domain_tags: list[str] | None = None,
    cross_role: bool = False,
    include_superseded: bool = False,
) -> SearchRequest:
    """Build a ``SearchRequest`` scoped to a role's defaults (scoped-default-on-read, §6).

    By default the request carries the seat's own ``role:`` tag (so it reads only
    role-attributed rows for that seat) plus the seat's default ``token_budget`` and
    ``payload_types`` allowlist. Pass ``cross_role=True`` to OPT OUT of the role tag and
    read across roles. Any explicit argument overrides the seat default.

    Args:
        role: A D-WS4-6 seat (e.g. ``"product-owner"``); must be in
            ``ROLE_RETRIEVAL_DEFAULTS``.
        project: Target project (already normalized; ``^[a-z0-9_]+$``).
        query: Optional semantic query.
        token_budget: Override the seat's default budget.
        payload_types: Override the seat's default allowlist. Unregistered names are
            dropped so the request validates.
        domain_tags: Extra facet tags (merged with the role tag unless ``cross_role``).
        cross_role: If True, omit the seat's ``role:`` tag (read cross-role).
        include_superseded: Passed through to the request.

    Returns:
        A validated ``SearchRequest``.

    Raises:
        KeyError: If ``role`` is not a known seat.
    """
    default = ROLE_RETRIEVAL_DEFAULTS[role]

    budget = default.token_budget if token_budget is None else token_budget

    if payload_types is None:
        resolved_types = _registered(default.payload_types)
    else:
        resolved_types = [pt for pt in payload_types if pt in PAYLOAD_REGISTRY]

    tags = list(domain_tags) if domain_tags else []
    if not cross_role:
        # Scoped-default-on-read: the seat reads its own role by default.
        rt = role_tag(role)
        if rt not in tags:
            tags.append(rt)

    return SearchRequest(
        project=project,
        payload_types=resolved_types,
        domain_tags=tags,
        query=query,
        token_budget=budget,
        include_superseded=include_superseded,
    )
