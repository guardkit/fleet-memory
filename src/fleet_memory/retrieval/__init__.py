"""Retrieval surface for fleet-memory search.

Defines the typed SearchRequest contract, validation rules, and search core.
Producer: TASK-RA-001 (SearchRequest), TASK-RA-002 (search core), TASK-RA-003 (assembly)
"""

from __future__ import annotations

from fleet_memory.retrieval.assembly import AssemblyResult, assemble_context
from fleet_memory.retrieval.core import SearchResult, search
from fleet_memory.retrieval.search_request import SearchRequest

__all__ = ["SearchRequest", "search", "SearchResult", "assemble_context", "AssemblyResult"]
