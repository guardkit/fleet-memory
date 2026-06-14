"""pytest-bdd glue for the Re-index Pipeline feature (FEAT-MEM-07).

Binds the scenarios in ``re-index-pipeline.feature`` so GuardKit's per-task
BDD oracle (``bdd_runner``) can collect them when it points pytest at the
literal ``.feature`` path via the ``features/conftest.py`` collection bridge.

Scaffolding state (TASK-AB-004 convention): step definitions are added
incrementally by the owning task for each ``@task:TASK-RIP-00x`` scenario.
Until a scenario's steps are implemented, pytest-bdd raises
``StepDefinitionNotFoundError`` for the first unbound step, which the bdd_runner
classifies as **pending** (tolerated — distinct from a failing assertion) rather
than a gate-blocking failure. As each task lands its steps, its scenario flips
from pending to passing.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import scenarios

# Bind every scenario in the feature file. The per-task ``-m`` marker filter
# (applied by bdd_runner) selects only the scenarios tagged for the running
# task; the rest are deselected.
scenarios("re-index-pipeline.feature")


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared mutable context for passing data between step definitions."""
    return {}
