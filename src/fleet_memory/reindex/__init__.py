"""Reindexing package for fleet-memory corpus processing.

This package provides manifest-driven, path-traversal-safe corpus walking and
document processing for the reindexing pipeline. The corpus manifest (exported
by guardkit) declares which directories this pipeline owns; only those roots
are ever walked.
"""

from fleet_memory.reindex.manifest import CorpusManifest, load_manifest
from fleet_memory.reindex.pipeline import RunReport, reindex_corpus
from fleet_memory.reindex.publisher import ReindexPublisher, publish_episode
from fleet_memory.reindex.walker import CorpusDocument, walk_corpus, walk_roots

__all__ = [
    "CorpusDocument",
    "CorpusManifest",
    "ReindexPublisher",
    "RunReport",
    "load_manifest",
    "publish_episode",
    "reindex_corpus",
    "walk_corpus",
    "walk_roots",
]
