"""Search returns one project's records and never another's (18 October 2026).

The factory's cards read memory for one project only (one sandbox per project,
design section 2.4a). Forge asks ``fleet_memory.retrieval.search`` for a single
granted project; this test proves, against a real ephemeral PostgreSQL +
pgvector store, that such a search returns that project's records and excludes
another project's records stored alongside them, even when both match the
query. Fake embeddings keep it deterministic; no embedding service is needed.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from fleet_memory.payloads.models import DocumentPayload
from fleet_memory.retrieval.core import search
from fleet_memory.retrieval.search_request import SearchRequest
from fleet_memory.writer.core import DeterministicWriter


def _identifiers(results) -> set[str]:
    # Keys are opaque ids; the stored value carries the record's identifier.
    return {str(result.value) for result in results}


@pytest.mark.integration
async def test_a_search_for_one_project_never_returns_another_projects_records(
    store_context, test_settings
) -> None:
    store, _ = store_context
    suffix = uuid4().hex[:8]
    project_a, project_b = f"scope_a_{suffix}", f"scope_b_{suffix}"
    writer = DeterministicWriter(store, test_settings)

    # The same words in both projects, so only the project filter can tell them apart.
    for project in (project_a, project_b):
        for n in range(3):
            await writer.write(
                DocumentPayload(
                    project=project,
                    identifier=f"{project}_build_outcome_{n}",
                    content=f"Build outcome {n}: the coach approved the health endpoint change.",
                    domain_tags=["build"],
                    source_ref="test_search_excludes_other_projects",
                )
            )

    def request(project: str) -> SearchRequest:
        return SearchRequest(
            project=project,
            query="build outcome coach approved health endpoint",
            token_budget=2000,
            payload_types=["document"],
        )

    for own, other in ((project_a, project_b), (project_b, project_a)):
        results = await search(request(own), store)
        # Positive control: the project's own records come back.
        assert results, f"a search for {own} returned nothing"
        assert {r.namespace[1] for r in results} == {own}
        found = " ".join(_identifiers(results))
        assert own in found
        # Exclusion: nothing of the other project, by namespace or by key.
        assert other not in found
        assert all(r.namespace[1] != other for r in results)


@pytest.mark.integration
async def test_a_project_with_no_records_gets_none_of_anothers(
    store_context, test_settings
) -> None:
    store, _ = store_context
    suffix = uuid4().hex[:8]
    stored, empty = f"scope_full_{suffix}", f"scope_empty_{suffix}"
    writer = DeterministicWriter(store, test_settings)
    await writer.write(
        DocumentPayload(
            project=stored,
            identifier=f"{stored}_build_outcome",
            content="Build outcome: the coach approved the health endpoint change.",
            domain_tags=["build"],
                    source_ref="test_search_excludes_other_projects",
        )
    )

    results = await search(
        SearchRequest(
            project=empty,
            query="build outcome coach approved health endpoint",
            token_budget=2000,
            payload_types=["document"],
        ),
        store,
    )
    assert results == []
