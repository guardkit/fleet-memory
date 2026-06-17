/feature-spec "Re-index pipeline: deterministic markdown-to-typed-payload parsers for guardkit seed modules, ADRs, review reports and task outcomes, publishing via nats-core MemoryEpisodeV1 through the live relay; idempotent full-corpus runs; backfill staging area for Fable-authored payloads with human review gate before publish"




I'll execute the feature-spec workflow. Starting with Phase 1: Context Gathering (silent).

Bash Detect stack and scan structure
IN
ls -la && echo "---STACK---" && ls pyproject.toml setup.py requirements.txt go.mod Cargo.toml 2>/dev/null && echo "---FEATURES---" && find . -name "*.feature" -not -path "*/node_modules/*" 2>/dev/null | head -20

OUT
Exit code 1
total 744
drwxr-xr-x   44 richardwoollcott  staff   1408 Jun 13 19:02 .
drwxr-xr-x  173 richardwoollcott  staff   5536 Jun 12 12:43 ..
drwxr-xr-x@  11 richardwoollcott  staff    352 Jun 12 16:41 .claude
-rw-r--r--    1 richardwoollcott  staff   1771 Jun 13 08:22 .env.example
drwxr-xr-x   17 richardwoollcott  staff    544 Jun 13 19:47 .git
-rw-r--r--@   1 richardwoollcott  staff   4723 Jun 12 13:02 .gitignore
drwxr-xr-x@  11 richardwoollcott  staff    352 Jun 13 19:02 .guardkit
-rw-r--r--    1 richardwoollcott  staff      0 Jun 13 08:22 .guardkit-git.lock
drwxr-xr-x@   6 richardwoollcott  staff    192 Jun 12 22:51 .pytest_cache
drwxr-xr-x@   7 richardwoollcott  staff    224 Jun 13 08:22 .venv
-rw-r--r--    1 richardwoollcott  staff  15711 Jun 13 08:22 coverage_all.json
-rw-r--r--    1 richardwoollcott  staff   2681 Jun 13 16:09 coverage_chunk_writer.json
-rw-r--r--    1 richardwoollcott  staff   3318 Jun 13 08:22 coverage_final.json
-rw-r--r--    1 richardwoollcott  staff  15663 Jun 13 08:22 coverage_integration.json
-rw-r--r--    1 richardwoollcott  staff  15663 Jun 13 08:22 coverage_phase4_new.json
-rw-r--r--    1 richardwoollcott  staff  15302 Jun 13 08:22 coverage_phase4_test.json
-rw-r--r--    1 richardwoollcott  staff  22820 Jun 13 08:22 coverage_phase4.json
-rw-r--r--    1 richardwoollcott  staff   9028 Jun 13 19:02 coverage_ra_002.json
-rw-r--r--    1 richardwoollcott  staff   4269 Jun 13 19:02 coverage_ra_004.json
-rw-r--r--    1 richardwoollcott  staff   2933 Jun 13 19:02 coverage_ra_005.json
-rw-r--r--    1 richardwoollcott  staff  70619 Jun 13 19:02 coverage_ra_007.json
-rw-r--r--    1 richardwoollcott  staff   3978 Jun 13 16:09 coverage_relay_service.json
-rw-r--r--    1 richardwoollcott  staff   3681 Jun 13 16:09 coverage_relay.json
-rw-r--r--    1 richardwoollcott  staff   5248 Jun 13 19:02 coverage_review.json
-rw-r--r--    1 richardwoollcott  staff   6729 Jun 13 13:49 coverage_task_dw_002.json
-rw-r--r--    1 richardwoollcott  staff   9524 Jun 13 13:49 coverage_task_dw_004.json
-rw-r--r--    1 richardwoollcott  staff   9578 Jun 13 13:49 coverage_task_dw_005.json
-rw-r--r--    1 richardwoollcott  staff   2300 Jun 13 12:25 coverage_task.json
-rw-r--r--    1 richardwoollcott  staff   3318 Jun 13 08:22 coverage_test.json
-rw-r--r--    1 richardwoollcott  staff  63341 Jun 13 19:02 coverage.json
drwxr-xr-x    4 richardwoollcott  staff    128 Jun 13 08:22 deploy
drwxr-xr-x@   4 richardwoollcott  staff    128 Jun 12 15:28 docs
drwxr-xr-x    8 richardwoollcott  staff    256 Jun 13 16:12 features
-rw-r--r--    1 richardwoollcott  staff   1065 Jun 12 12:43 LICENSE
drwxr-xr-x@   2 richardwoollcott  staff     64 Jun 12 15:18 migrations
-rw-r--r--    1 richardwoollcott  staff   1207 Jun 13 19:02 pyproject.toml
-rw-r--r--    1 richardwoollcott  staff     38 Jun 12 12:43 README.md
drwxr-xr-x    4 richardwoollcott  staff    128 Jun 13 08:22 src
drwxr-xr-x@   8 richardwoollcott  staff    256 Jun 13 08:22 tasks
-rw-r--r--    1 richardwoollcott  staff  10326 Jun 13 08:22 test_all_output.txt
-rw-r--r--    1 richardwoollcott  staff   3192 Jun 13 08:22 test_integration_output.txt
-rw-r--r--    1 richardwoollcott  staff  10645 Jun 13 08:22 test_output.txt
-rw-r--r--    1 richardwoollcott  staff   5646 Jun 13 08:22 test_phase4_output.txt
drwxr-xr-x   10 richardwoollcott  staff    320 Jun 13 12:25 tests
---STACK---
pyproject.toml
Bash Find source layout and MemoryEpisodeV1
IN
echo "---SRC---" && find src -maxdepth 3 -type d 2>/dev/null | head -40 && echo "---MODELS/SCHEMA---" && grep -rl "MemoryEpisodeV1" --include="*.py" . 2>/dev/null | head -20

OUT
---SRC---
src
src/fleet_memory
src/fleet_memory.egg-info
src/fleet_memory/payloads
src/fleet_memory/__pycache__
src/fleet_memory/writer
src/fleet_memory/retrieval
src/fleet_memory/relay
---MODELS/SCHEMA---
.guardkit/worktrees/FEAT-MEM-06/tests/unit/relay/test_handler.py
.guardkit/worktrees/FEAT-MEM-06/tests/unit/relay/test_service.py
.guardkit/worktrees/FEAT-MEM-06/tests/unit/relay/test_schema.py
.guardkit/worktrees/FEAT-MEM-06/src/fleet_memory/relay/handler.py
.guardkit/worktrees/FEAT-MEM-06/src/fleet_memory/relay/schema.py
.guardkit/worktrees/FEAT-MEM-06/src/fleet_memory/relay/service.py
tests/unit/relay/test_service.py
tests/unit/relay/test_schema.py
tests/unit/relay/test_handler.py
src/fleet_memory/relay/service.py
src/fleet_memory/relay/handler.py
src/fleet_memory/relay/schema.py
I'll explore the codebase structure, schemas, and existing features in parallel.

Bash List fleet_memory python modules
IN
echo "===FLEET_MEMORY TREE==="; find src/fleet_memory -name "*.py" -not -path "*__pycache__*" | sort; echo "===PAYLOADS==="; ls -la src/fleet_memory/payloads/ 2>/dev/null

OUT
===FLEET_MEMORY TREE===
src/fleet_memory/__init__.py
src/fleet_memory/app.py
src/fleet_memory/embed.py
src/fleet_memory/errors.py
src/fleet_memory/payloads/__init__.py
src/fleet_memory/payloads/base.py
src/fleet_memory/payloads/models.py
src/fleet_memory/payloads/registry.py
src/fleet_memory/relay/__init__.py
src/fleet_memory/relay/chunk_writer.py
src/fleet_memory/relay/chunker.py
src/fleet_memory/relay/handler.py
src/fleet_memory/relay/schema.py
src/fleet_memory/relay/service.py
src/fleet_memory/retrieval/__init__.py
src/fleet_memory/retrieval/assembly.py
src/fleet_memory/retrieval/composition.py
src/fleet_memory/retrieval/core.py
src/fleet_memory/retrieval/probe_harness.py
src/fleet_memory/retrieval/search_request.py
src/fleet_memory/settings.py
src/fleet_memory/store.py
src/fleet_memory/writer/__init__.py
src/fleet_memory/writer/core.py
src/fleet_memory/writer/identity.py
src/fleet_memory/writer/supersession.py
===PAYLOADS===
total 40
-rw-r--r--   1 richardwoollcott  staff   437 Jun 13 12:25 __init__.py
drwxr-xr-x   6 richardwoollcott  staff   192 Jun 13 12:25 .
drwxr-xr-x  13 richardwoollcott  staff   416 Jun 13 19:02 ..
-rw-r--r--   1 richardwoollcott  staff  5900 Jun 13 12:25 base.py
-rw-r--r--   1 richardwoollcott  staff  2677 Jun 13 12:25 models.py
-rw-r--r--   1 richardwoollcott  staff  2154 Jun 13 12:25 registry.py
Bash List existing feature specs
IN
echo "===EXISTING FEATURES==="; ls -la features/; echo "===FEATURE DIRS==="; find features -maxdepth 2 -type f | sort

OUT
===EXISTING FEATURES===
total 0
drwxr-xr-x   8 richardwoollcott  staff   256 Jun 13 16:12 .
drwxr-xr-x  44 richardwoollcott  staff  1408 Jun 13 19:02 ..
drwxr-xr-x   5 richardwoollcott  staff   160 Jun 13 12:34 deterministic-writer
drwxr-xr-x   5 richardwoollcott  staff   160 Jun 13 19:08 memory-mcp-server
drwxr-xr-x   5 richardwoollcott  staff   160 Jun 13 14:20 relay-integration
drwxr-xr-x   5 richardwoollcott  staff   160 Jun 13 19:02 retrieval-api
drwxr-xr-x   5 richardwoollcott  staff   160 Jun 13 08:22 storage-substrate
drwxr-xr-x   5 richardwoollcott  staff   160 Jun 13 10:46 typed-payload-registry
===FEATURE DIRS===
features/deterministic-writer/deterministic-writer_assumptions.yaml
features/deterministic-writer/deterministic-writer_summary.md
features/deterministic-writer/deterministic-writer.feature
features/memory-mcp-server/memory-mcp-server_assumptions.yaml
features/memory-mcp-server/memory-mcp-server_summary.md
features/memory-mcp-server/memory-mcp-server.feature
features/relay-integration/relay-integration_assumptions.yaml
features/relay-integration/relay-integration_summary.md
features/relay-integration/relay-integration.feature
features/retrieval-api/retrieval-api_assumptions.yaml
features/retrieval-api/retrieval-api_summary.md
features/retrieval-api/retrieval-api.feature
features/storage-substrate/storage-substrate_assumptions.yaml
features/storage-substrate/storage-substrate_summary.md
features/storage-substrate/storage-substrate.feature
features/typed-payload-registry/typed-payload-registry_assumptions.yaml
features/typed-payload-registry/typed-payload-registry_summary.md
features/typed-payload-registry/typed-payload-registry.feature
Bash Read relay schema MemoryEpisodeV1
IN
echo "===SCHEMA==="; cat src/fleet_memory/relay/schema.py 2>/dev/null | head -120

OUT
===SCHEMA===
"""Pydantic message schemas for relay stream processing.

Defines the inbound MemoryEpisodeV1 envelope, ContentFormat enum, and Chunk
value object consumed by downstream relay tasks.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class ContentFormat(str, Enum):
    """Recognized content formats for memory episodes.

    Only these three formats are recognized by the chunker.
    Unrecognized formats are parked at routing time (negative scenario).
    """

    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"


class MemoryEpisodeV1(BaseModel):
    """Inbound envelope published by nats-core onto the MEMORY stream.

    This is the producer-side contract for memory episodes.
    The content_format field is stored as-is (raw string) to allow
    unrecognized values to survive parse and be routed/parked downstream.
    """

    model_config = ConfigDict(extra="ignore")  # Forward compatibility

    episode_id: str
    project: str
    content_format: str  # Raw string, NOT validated against ContentFormat enum
    body: str
    payload_type: str | None = None
    source_ref: str | None = None


class Chunk(BaseModel):
    """Frozen value object produced by chunker and consumed by chunk writer.

    Represents a single chunk of text extracted from a memory episode.
    No storage logic — pure data transfer object.
    """

    model_config = ConfigDict(frozen=True)  # Immutable

    index: int
    text: str
    source_ref: str | None
    project: str
Now let me read the payload models, an existing feature for convention, and the FEAT-MEM-06 spec.

Bash Read payload models and registry
IN
echo "===MODELS==="; cat src/fleet_memory/payloads/models.py; echo "===REGISTRY==="; cat src/fleet_memory/payloads/registry.py; echo "===BASE(head)==="; head -60 src/fleet_memory/payloads/base.py

OUT
===MODELS===
"""Concrete payload type models for fleet-memory typed payload registry.

Implements seven canonical payload types that subclass BasePayload:
adr, review_report, build_outcome, pattern, warning, seed_module, document.

Each type declares its canonical payload_type and type-specific required fields.
Shared conventions (identifiers, supersession, domain tags) are inherited from BasePayload.
"""

from __future__ import annotations

from typing import ClassVar

from fleet_memory.payloads.base import BasePayload


class ADRPayload(BasePayload):
    """Architecture Decision Record payload.

    Tracks architectural decisions with decision text and status.
    """

    payload_type: ClassVar[str] = "adr"

    decision: str  # The architectural decision being documented
    status: str  # e.g., "proposed", "accepted", "deprecated", "superseded"


class ReviewReportPayload(BasePayload):
    """Code review or audit report payload.

    Requires a verdict field (e.g., "approved", "rejected", "needs_changes").
    """

    payload_type: ClassVar[str] = "review_report"

    verdict: str  # Required: the review outcome


class BuildOutcomePayload(BasePayload):
    """Build or CI pipeline outcome payload.

    Tracks build status and duration.
    """

    payload_type: ClassVar[str] = "build_outcome"

    status: str  # e.g., "success", "failure", "timeout"
    duration_seconds: int  # Build execution time


class PatternPayload(BasePayload):
    """Design pattern or architectural pattern payload.

    Documents patterns with name and category.
    """

    payload_type: ClassVar[str] = "pattern"

    pattern_name: str  # e.g., "Singleton", "Factory", "Observer"
    category: str  # e.g., "creational", "structural", "behavioral"


class WarningPayload(BasePayload):
    """Warning or alert payload.

    Tracks warnings with severity and message.
    """

    payload_type: ClassVar[str] = "warning"

    severity: str  # e.g., "low", "medium", "high", "critical"
    message: str  # Human-readable warning description


class SeedModulePayload(BasePayload):
    """Seed module or bootstrap component payload.

    Tracks foundational modules with their path.
    """

    payload_type: ClassVar[str] = "seed_module"

    module_path: str  # Path to the module (e.g., "src/auth", "lib/core")


class DocumentPayload(BasePayload):
    """Generic document payload (catch-all type).

    Accepts payloads with no type-specific fields beyond BasePayload requirements.
    This is the fallback type for content that doesn't fit other categories.
    """

    payload_type: ClassVar[str] = "document"

    # No type-specific fields - inherits only BasePayload fields
===REGISTRY===
"""Payload dispatch registry for typed payload serialization and round-trip.

Maps canonical payload_type names to model classes (bijection).
Supports name→model lookup, model→name reverse lookup, and serialize→rebuild round trip.

Producer: TASK-TPR-003
Consumer: FEAT-MEM-03 (deterministic writer), FEAT-MEM-04 (relay consumer)
"""

from __future__ import annotations

from fleet_memory.errors import UnknownPayloadTypeError
from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.models import (
    ADRPayload,
    BuildOutcomePayload,
    DocumentPayload,
    PatternPayload,
    ReviewReportPayload,
    SeedModulePayload,
    WarningPayload,
)

# Bijective registry: each canonical payload_type name maps to exactly one model class
PAYLOAD_REGISTRY: dict[str, type[BasePayload]] = {
    "adr": ADRPayload,
    "review_report": ReviewReportPayload,
    "build_outcome": BuildOutcomePayload,
    "pattern": PatternPayload,
    "warning": WarningPayload,
    "seed_module": SeedModulePayload,
    "document": DocumentPayload,
}

# Reverse lookup cache: model class → canonical type name
_MODEL_TO_TYPE: dict[type[BasePayload], str] = {
    model: name for name, model in PAYLOAD_REGISTRY.items()
}


def get_model_for_type(payload_type: str) -> type[BasePayload]:
    """Resolve payload_type name to model class.

    Args:
        payload_type: Canonical type name (case-sensitive)

    Returns:
        The model class for this payload type

    Raises:
        UnknownPayloadTypeError: If payload_type is not registered (ASSUM-010)
    """
    if payload_type not in PAYLOAD_REGISTRY:
        raise UnknownPayloadTypeError(payload_type)
    return PAYLOAD_REGISTRY[payload_type]


def get_type_for_model(model: type[BasePayload]) -> str:
    """Reverse lookup: model class to canonical type name.

    Args:
        model: A payload model class

    Returns:
        The canonical payload_type name

    Raises:
        ValueError: If model is not registered
    """
    if model not in _MODEL_TO_TYPE:
        raise ValueError(f"Model {model} is not registered in PAYLOAD_REGISTRY")
    return _MODEL_TO_TYPE[model]
===BASE(head)===
"""Base payload model and validators for typed payload registry.

Defines BasePayload with natural key construction, identifier validation,
and supersession rules. All concrete payload types inherit from BasePayload.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, computed_field

# Regex pattern matching existing NamespaceValidationError convention
# Allows uppercase to support identifiers like ADR_SP_007 from the feature file
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_identifier(field_name: str, value: str) -> None:
    """Validate an identifier uses underscores only.

    Args:
        field_name: Name of the field being validated
        value: The identifier value

    Raises:
        IdentifierValidationError: If invalid
    """
    if not value:
        raise IdentifierValidationError(field_name, value)
    if not IDENTIFIER_PATTERN.match(value):
        raise IdentifierValidationError(field_name, value)


class IdentifierValidationError(ValueError):
    """Raised when project or identifier contains invalid characters.

    Identifiers must use underscores only (match ^[a-z0-9_]+$), no hyphens or colons.
    Follows the same pattern as NamespaceValidationError from errors.py.
    """

    def __init__(self, field_name: str, value: str) -> None:
        """Initialize with field name and invalid value.

        Args:
            field_name: The field that failed validation (project or identifier)
            value: The invalid value that was rejected
        """
        if not value:
            super().__init__(f"{field_name} identifier is required and cannot be empty")
        else:
            super().__init__(
                f"Invalid {field_name} identifier '{value}': identifiers must use "
                f"underscores only (match ^[a-zA-Z0-9_]+$)"
            )
        self.field_name = field_name
        self.value = value


class SupersessionValidationError(ValueError):
Bash Read feature yaml and find ADRs
IN
echo "===FEAT-MEM-06 yaml==="; cat .guardkit/features/FEAT-MEM-06.yaml 2>/dev/null; echo; echo "===ADRs==="; find . -iname "*adr*" -not -path "*/.git/*" -not -path "*/worktrees/*" | head; find docs -type f 2>/dev/null | head -30

OUT
===FEAT-MEM-06 yaml===
id: FEAT-MEM-06
name: Memory MCP Server
description: 'FEAT-MEM-06 FastMCP server over stdio: memory_search, memory_write_payload,
  memory_supersede tools plus a memory://projects resource, layered over the FEAT-MEM-05
  retrieval API and the FEAT-MEM-03 deterministic writer. Single write path (byte-identical
  to relay writes); failures surfaced as structured tool-error results (graceful degradation,
  no crash).'
created: '2026-06-13T19:06:07.479915'
status: in_progress
complexity: 6
estimated_tasks: 7
tasks:
- id: TASK-MCP-001
  name: Scaffold FastMCP server add fastmcp dep wire lifespan
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-001-scaffold-fastmcp-server.md
  complexity: 5
  dependencies: []
  status: in_progress
  implementation_mode: task-work
  estimated_minutes: 75
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 1
  started_at: '2026-06-13T19:16:03.750801'
  completed_at: null
- id: TASK-MCP-002
  name: Shared tool-error and degradation envelope
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-002-tool-error-degradation-envelope.md
  complexity: 4
  dependencies:
  - TASK-MCP-001
  status: pending
  implementation_mode: task-work
  estimated_minutes: 50
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 0
  started_at: null
  completed_at: null
- id: TASK-MCP-003
  name: memory_search tool over retrieval API
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-003-memory-search-tool.md
  complexity: 5
  dependencies:
  - TASK-MCP-002
  status: pending
  implementation_mode: task-work
  estimated_minutes: 75
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 0
  started_at: null
  completed_at: null
- id: TASK-MCP-004
  name: memory_write_payload tool through deterministic writer
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-004-memory-write-payload-tool.md
  complexity: 6
  dependencies:
  - TASK-MCP-002
  status: pending
  implementation_mode: task-work
  estimated_minutes: 113
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 0
  started_at: null
  completed_at: null
- id: TASK-MCP-005
  name: memory_supersede tool declared supersession
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-005-memory-supersede-tool.md
  complexity: 5
  dependencies:
  - TASK-MCP-002
  status: pending
  implementation_mode: task-work
  estimated_minutes: 75
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 0
  started_at: null
  completed_at: null
- id: TASK-MCP-006
  name: memory projects listing resource
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-006-projects-resource.md
  complexity: 3
  dependencies:
  - TASK-MCP-002
  status: pending
  implementation_mode: direct
  estimated_minutes: 33
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 0
  started_at: null
  completed_at: null
- id: TASK-MCP-007
  name: Wire BDD scenario suite and integration tests
  file_path: tasks/backlog/memory-mcp-server/TASK-MCP-007-bdd-and-integration-tests.md
  complexity: 5
  dependencies:
  - TASK-MCP-003
  - TASK-MCP-004
  - TASK-MCP-005
  - TASK-MCP-006
  status: pending
  implementation_mode: task-work
  estimated_minutes: 75
  requires_infrastructure: []
  result: null
  turns_completed: 0
  current_turn: 0
  started_at: null
  completed_at: null
orchestration:
  parallel_groups:
  - - TASK-MCP-001
  - - TASK-MCP-002
  - - TASK-MCP-003
    - TASK-MCP-004
    - TASK-MCP-005
    - TASK-MCP-006
  - - TASK-MCP-007
  estimated_duration_minutes: 496
  recommended_parallel: 4
smoke_gates:
  after_wave:
  - 3
  - 4
  command: 'set -e

    pytest tests/unit tests/bdd -x

    '
  expected_exit: 0
  timeout: 180
  exit5_is_hard_fail: false
preflight_strict: false
evidence_repos: []
execution:
  started_at: '2026-06-13T19:16:03.369589'
  completed_at: null
  worktree_path: /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.guardkit/worktrees/FEAT-MEM-06
  total_turns: 0
  tasks_completed: 0
  tasks_failed: 0
  current_wave: 1
  completed_waves: []
  last_updated: '2026-06-13T19:16:03.750815'
  archived_at: null
  archived_to: null

===ADRs===
docs/runbooks/RUNBOOK-nas-postgres-deploy.md
docs/research/ideas/phase-core-build-plan.md
docs/research/ideas/phase-core-scope.md
Let me read the publish path, deterministic writer, and an existing feature spec for convention.

Bash Read relay service and writer core
IN
echo "===RELAY SERVICE==="; cat src/fleet_memory/relay/service.py; echo "===WRITER CORE (head 80)==="; head -80 src/fleet_memory/writer/core.py

OUT
===RELAY SERVICE===
"""RelayService: content_format routing and two-layer idempotency.

The brain of the relay with zero NATS imports (pure service — testable by direct instantiation).
Routes episodes based on content_format (json/markdown/text) and maps exceptions to
poison (deterministic failures) vs transient (recoverable failures).

Producer: TASK-RLY-005
Consumer: FEAT-MEM-04 (relay ingestion)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import ValidationError

from fleet_memory.errors import (
    EmbedDimensionError,
    EmbedServiceError,
    EmbedTimeoutError,
    NamespaceValidationError,
    PoisonEpisodeError,
    TransientIngestError,
    UnknownPayloadTypeError,
)
from fleet_memory.payloads.base import IdentifierValidationError
from fleet_memory.payloads.registry import get_model_for_type
from fleet_memory.relay.chunker import chunk_prose

if TYPE_CHECKING:
    from fleet_memory.relay.chunk_writer import ChunkWriter
    from fleet_memory.relay.schema import MemoryEpisodeV1
    from fleet_memory.settings import Settings
    from fleet_memory.writer.core import DeterministicWriter


class RelayService:
    """Pure service for memory episode ingestion with content_format routing.

    Routes episodes based on content_format:
    - json → typed payload via registry → DeterministicWriter (idempotency layer 1)
    - markdown/text → chunk_prose → ChunkWriter (idempotency layer 2)
    - anything else → PoisonEpisodeError

    Exception mapping (correctness core):
    - Deterministic failures → PoisonEpisodeError (DLQ)
    - Recoverable failures → TransientIngestError (nak + redeliver)
    - Unenumerated exceptions → TransientIngestError (default-to-transient policy)

    Args:
        writer: DeterministicWriter for structured json payloads
        chunk_writer: ChunkWriter for prose chunks
        settings: Configuration (chunking params, etc.)
    """

    def __init__(
        self,
        writer: DeterministicWriter,
        chunk_writer: ChunkWriter,
        settings: Settings,
    ) -> None:
        """Initialize service with collaborators.

        Args:
            writer: DeterministicWriter instance
            chunk_writer: ChunkWriter instance
            settings: Settings instance
        """
        self.writer = writer
        self.chunk_writer = chunk_writer
        self.settings = settings

    async def ingest(self, episode: MemoryEpisodeV1) -> None:
        """Ingest a memory episode with content_format-based routing.

        Routes based on episode.content_format:
        - "json" → _ingest_json (structured path)
        - "markdown" or "text" → _ingest_prose (chunking path)
        - anything else → PoisonEpisodeError

        Returns only after durable write commits. Clean return signals handler to ack.

        Args:
            episode: MemoryEpisodeV1 envelope from NATS stream

        Raises:
            PoisonEpisodeError: Deterministic failure (unparseable, validation,
                unknown type/format, namespace violation, dimension mismatch)
            TransientIngestError: Recoverable failure (service unavailable,
                timeout, connection error, or any unenumerated exception)
        """
        try:
            # Route based on content_format
            if episode.content_format == "json":
                await self._ingest_json(episode)
            elif episode.content_format in ("markdown", "text"):
                await self._ingest_prose(episode)
            else:
                # Unrecognized format → poison
                raise PoisonEpisodeError(
                    reason=f"unrecognized content_format: {episode.content_format}",
                    detail="Only json, markdown, and text are supported",
                )

        # Exception mapping: deterministic failures → PoisonEpisodeError
        except PoisonEpisodeError:
            # Already poison, re-raise as-is
            raise
        except UnknownPayloadTypeError as e:
            # Unknown payload_type → poison
            raise PoisonEpisodeError(
                reason=f"unknown payload_type: {e.payload_type}",
                detail="Not found in dispatch registry",
            ) from e
        except NamespaceValidationError as e:
            # Hyphenated project or invalid namespace → poison
            raise PoisonEpisodeError(
                reason=f"invalid namespace: {e.invalid_parts}",
                detail=f"Namespace {e.namespace} contains invalid identifiers",
            ) from e
        except IdentifierValidationError as e:
            # Invalid project or identifier (hyphens, etc.) → poison
            raise PoisonEpisodeError(
                reason=f"invalid {e.field_name} identifier: {e.value}",
                detail="Identifiers must use underscores only",
            ) from e
        except ValidationError as e:
            # Pydantic validation failure → poison
            raise PoisonEpisodeError(
                reason="payload validation failed",
                detail=str(e),
            ) from e
        except EmbedDimensionError as e:
            # Wrong dimension → poison (deterministic config mismatch)
            raise PoisonEpisodeError(
                reason=f"embedding dimension mismatch: {e.actual} != {e.expected}",
                detail="Check embed_dims configuration",
            ) from e

        # Exception mapping: recoverable failures → TransientIngestError
        except (EmbedServiceError, EmbedTimeoutError) as e:
            # Embedding service issues → transient
            raise TransientIngestError(
                message=f"Embedding service unavailable: {e}",
            ) from e
        except (ConnectionError, TimeoutError) as e:
            # Network/connection issues → transient
            raise TransientIngestError(
                message=f"Connection error: {e}",
            ) from e

        # Default-to-transient: any unenumerated exception → transient
        # Losing data is worse than redelivering
        except Exception as e:
            raise TransientIngestError(
                message=f"Unexpected error during ingest: {e}",
            ) from e

    async def _ingest_json(self, episode: MemoryEpisodeV1) -> None:
        """Ingest structured json episode via typed payload registry.

        Algorithm:
        1. Validate payload_type is present
        2. Parse body as JSON
        3. Resolve payload model via registry
        4. Construct and validate typed payload
        5. Write via DeterministicWriter (idempotency layer 1)

        Args:
            episode: Episode with content_format="json"

        Raises:
            PoisonEpisodeError: If payload_type is None
            UnknownPayloadTypeError: If payload_type not in registry
            ValidationError: If payload validation fails
            json.JSONDecodeError: If body is not valid JSON
        """
        # Step 1: Validate payload_type is present
        if episode.payload_type is None:
            raise PoisonEpisodeError(
                reason="missing payload_type for json episode",
                detail="json episodes must specify payload_type",
            )

        # Step 2: Parse body as JSON
        try:
            payload_dict = json.loads(episode.body)
        except json.JSONDecodeError as e:
            raise PoisonEpisodeError(
                reason="unparseable json body",
                detail=str(e),
            ) from e

        # Step 3: Resolve payload model via registry
        payload_model = get_model_for_type(episode.payload_type)

        # Step 4: Construct and validate typed payload
        # ValidationError propagates up to be caught by ingest()
        payload = payload_model(**payload_dict)

        # Step 5: Write via DeterministicWriter
        # DeterministicWriter.write() implements idempotency via content-hash upsert
        await self.writer.write(payload)

    async def _ingest_prose(self, episode: MemoryEpisodeV1) -> None:
        """Ingest markdown/text episode via chunking pipeline.

        Algorithm:
        1. Chunk body via chunk_prose (heading-aware, overlapping)
        2. Write chunks via ChunkWriter (idempotency layer 2: uuid5 keys)

        Empty body → zero chunks → clean return (success, no error).

        Args:
            episode: Episode with content_format="markdown" or "text"
        """
        # Step 1: Chunk prose with settings-driven params
        chunks = chunk_prose(
            episode.body,
            target_tokens=self.settings.chunk_target_tokens,
            overlap_ratio=self.settings.chunk_overlap_ratio,
            source_ref=episode.source_ref,
            project=episode.project,
        )

        # Step 2: Write chunks (idempotent via uuid5(episode_id, index))
        # Empty chunks list is allowed and results in no writes
        await self.chunk_writer.write_chunks(episode.episode_id, chunks)
===WRITER CORE (head 80)===
"""Deterministic writer core: idempotent content-hash upsert.

Provides DeterministicWriter that transforms typed payloads into AsyncPostgresStore
records with zero language-model calls. Identity comes from TASK-DW-001;
persistence and embed-on-write go through AsyncPostgresStore; input validation
uses the typed payload registry.

Producer: TASK-DW-002
Consumer: FEAT-MEM-03 (deterministic write API)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fleet_memory.payloads.base import BasePayload
from fleet_memory.payloads.registry import PAYLOAD_REGISTRY
from fleet_memory.store import validate_namespace
from fleet_memory.writer.identity import content_hash, record_identity
from fleet_memory.writer.supersession import (
    apply_supersessions,
    check_and_apply_forward_supersession,
)

if TYPE_CHECKING:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from fleet_memory.settings import Settings


class DeterministicWriter:
    """Deterministic writer with idempotent content-hash upsert.

    Transforms typed payloads into AsyncPostgresStore records with no LLM calls.
    Implements version-aware upsert: no-op for identical content, version++ for changes.

    Args:
        store: Configured AsyncPostgresStore with embed-on-write enabled
        settings: Configuration (used for validation and metadata)
    """

    def __init__(self, store: AsyncPostgresStore, settings: Settings) -> None:
        """Initialize writer with store and settings.

        Args:
            store: AsyncPostgresStore instance (already configured with embedding)
            settings: Settings instance for validation
        """
        self.store = store
        self.settings = settings

    async def write(self, payload: BasePayload) -> None:
        """Write a single typed payload with idempotent content-hash upsert.

        Algorithm:
        1. Validate payload is registered
        2. Build and validate namespace
        3. Compute identity and content_hash
        4. Check for existing record
        5. Apply upsert logic (no-op if same hash, version++ if different)
        6. Apply declared supersessions (if any)

        Args:
            payload: A registered BasePayload subclass instance

        Raises:
            ValueError: If payload type is not registered
            NamespaceValidationError: If namespace contains invalid identifiers
            RuntimeError: If embedding service unavailable or database unreachable
        """
        # Step 1: Validate payload is registered
        payload_type = payload.payload_type
        if payload_type not in PAYLOAD_REGISTRY:
            raise ValueError(
                f"Payload type '{payload_type}' is not a recognized payload type. "
                f"Only registered BasePayload subclasses can be written."
            )

        # Step 2: Build namespace and validate before any store operation
Bash Read existing feature for convention
IN
echo "===relay-integration.feature==="; cat features/relay-integration/relay-integration.feature; echo; echo "===deterministic-writer summary==="; cat features/deterministic-writer/deterministic-writer_summary.md

OUT
===relay-integration.feature===
# Generated by /feature-spec
# Feature: Relay Integration (FEAT-MEM-04)
# Stack: python
# Assumptions: 11 (see relay-integration_assumptions.yaml)
# Generated: 2026-06-13T11:04:22Z
#
# Context sources: docs/research/ideas/phase-core-build-plan.md (FEAT-MEM-04),
# docs/research/ideas/phase-core-scope.md, features/typed-payload-registry/typed-payload-registry.feature,
# features/deterministic-writer/deterministic-writer.feature, src/fleet_memory/store.py, src/fleet_memory/embed.py
#
# Relay ack/nak/DLQ semantics (D5/D9) and max_deliver inherit from the
# nats-infrastructure memory-relay scope, which is not readable from this repo;
# those values are carried here as low-confidence assumptions for Coach review.
#
# Background applies: every scenario assumes the durable consumer is subscribed
# to the MEMORY stream with the registry, writer, embedding service, and store available.

@relay-integration
Feature: Relay Integration
  As the fleet-memory relay consumer on the MEMORY stream
  I want every published MemoryEpisodeV1 routed by its content format — structured payloads through the registry to the deterministic writer, prose chunked and embedded — and acknowledged only once durably stored, with poison episodes parked and redeliveries made inert
  So that capture is fire-and-forget and lossless, no episode is silently dropped, no language model touches the write path, and at-least-once redelivery can never duplicate a memory

  Background:
    Given the relay consumer is subscribed to the MEMORY stream as a durable consumer
    And the typed payload registry and deterministic writer are available
    And the embedding service and store are available

  # ───────────────────────── Key examples ────────────────────────────

  # Why: Core structured path — content_format json dispatches through the registry to the writer
  @task:TASK-RLY-005
  @key-example @smoke
  Scenario: A structured JSON episode is dispatched through the registry to the deterministic writer
    Given a MemoryEpisodeV1 whose content format is structured JSON for a known payload type
    When the consumer receives the episode
    Then the payload should be dispatched through the registry to the deterministic writer
    And a typed record for that payload should exist in the project namespace
    And the episode should be acknowledged

  # Why: Core prose path — markdown is chunked heading-aware, embedded, and stored as chunks
  @task:TASK-RLY-005
  @key-example @smoke
  Scenario: A markdown episode is chunked, embedded, and stored as chunks under the project chunk namespace
    Given a MemoryEpisodeV1 whose content format is markdown for project "guardkit"
    When the consumer receives the episode
    Then the body should be split into heading-aware chunks
    And each chunk should be embedded and stored under the project chunk namespace
    And the episode should be acknowledged

  # Why: Plain text takes the same chunk+embed path as markdown (RD-7 — unstructured = chunk+embed)
  @task:TASK-RLY-005
  @key-example
  Scenario: A plain text episode is chunked and embedded on the same path as markdown
    Given a MemoryEpisodeV1 whose content format is plain text
    When the consumer receives the episode
    Then the body should be chunked and embedded and stored as chunks
    And the episode should be acknowledged

  # Why: Content format is the routing key — it alone selects which write path runs
  @task:TASK-RLY-005
  @key-example @smoke
  Scenario Outline: The episode content format selects the write path
    Given a MemoryEpisodeV1 whose content format is "<format>"
    When the consumer receives the episode
    Then it should be processed by the "<path>" path

    Examples:
      | format   | path       |
      | json     | structured |
      | markdown | chunk      |
      | text     | chunk      |

  # Why: The headline acceptance criterion — a mixed batch produces typed records and chunks together
  @task:TASK-RLY-005
  @key-example @smoke
  Scenario: A mixed batch of structured and prose episodes yields typed records and chunks
    Given 3 structured JSON episodes for known payload types
    And 2 markdown episodes
    When the consumer processes all five episodes
    Then 3 typed records should exist
    And the markdown episodes should produce one or more chunks
    And all five episodes should be acknowledged

  # Why: Ack-after-commit is what makes at-least-once delivery safe — nothing is acked until it is durable
  # [ASSUMPTION: confidence=medium] An episode is acknowledged only after its write has durably committed to the store
  @task:TASK-RLY-006
  @key-example @smoke
  Scenario: An episode is acknowledged only after it is durably stored
    Given a MemoryEpisodeV1 ready to process
    When the consumer processes the episode
    Then the episode should not be acknowledged before its write has committed
    And it should be acknowledged once the write has committed

  # Why: Provenance must survive ingestion — every chunk traces back to its source episode
  @task:TASK-RLY-004
  @key-example
  Scenario: Each stored chunk carries the source reference and project of its originating episode
    Given a markdown episode for project "guardkit" with a known source reference
    When the consumer processes the episode
    Then every resulting chunk should record that source reference
    And every resulting chunk should be stored in the "guardkit" project namespace

  # ───────────────────── Boundary conditions ─────────────────────────

  # Why: Chunk-count boundary — content below, at, and above one chunk produces the expected chunk counts
  # [ASSUMPTION: confidence=medium] Target chunk size is approximately 1000 tokens (OD-1 starting value)
  @task:TASK-RLY-003
  @boundary
  Scenario Outline: Prose content produces a chunk count proportional to its size
    Given a markdown episode whose body is <size>
    When the consumer processes the episode
    Then it should produce <chunks> chunk(s)

    Examples:
      | size                 | chunks   |
      | well under one chunk | 1        |
      | exactly one chunk    | 1        |
      | just over one chunk  | 2        |
      | several chunks long  | multiple |

  # Why: Just-inside overlap — adjacent chunks must share overlapping content so meaning is not severed at a cut
  # [ASSUMPTION: confidence=medium] Adjacent chunks overlap by approximately 15% of chunk size (OD-1 starting value)
  @task:TASK-RLY-003
  @boundary
  Scenario: Adjacent chunks of a multi-chunk document share overlapping content
    Given a markdown episode long enough to span at least two chunks
    When the consumer processes the episode
    Then each chunk after the first should begin with content overlapping the previous chunk

  # Why: Heading awareness — a chunk boundary should prefer a heading break over splitting mid-section
  @task:TASK-RLY-003
  @boundary
  Scenario: Chunk boundaries prefer heading breaks over splitting a section mid-sentence
    Given a markdown episode with multiple headings and sections
    When the consumer processes the episode
    Then chunk boundaries should fall at heading breaks where possible
    And no heading line should be separated from the section it introduces

  # Why: Empty-body boundary — an episode with no usable content produces no chunks but is still accounted for
  # [ASSUMPTION: confidence=low] An episode whose body is empty or whitespace-only produces zero chunks and is acknowledged, not parked
  @task:TASK-RLY-005
  @boundary
  Scenario: A prose episode with an empty body produces no chunks and is acknowledged
    Given a markdown episode whose body is empty
    When the consumer processes the episode
    Then no chunk should be created
    And the episode should be acknowledged

  # Why: Just-inside redelivery — a transient failure short of the delivery limit is retried, not parked
  # [ASSUMPTION: confidence=low] The consumer parks an episode only after max_deliver attempts; max_deliver is 5
  @task:TASK-RLY-006
  @boundary
  Scenario: An episode that has failed fewer than the delivery limit is redelivered, not parked
    Given an episode that has been delivered 4 times without being acknowledged
    When it is delivered once more and processing succeeds
    Then the episode should be acknowledged
    And it should not be sent to the dead-letter subject

  # Why: Just-outside redelivery — the attempt that reaches the limit parks the episode
  @task:TASK-RLY-006
  @boundary @negative
  Scenario: An episode that reaches the delivery limit is parked on the dead-letter subject
    Given an episode that keeps failing on every delivery
    When it has been delivered the maximum number of times
    Then the episode should be sent to the dead-letter subject
    And the consumer should continue processing other episodes

  # ─────────────────────── Negative cases ────────────────────────────

  # Why: A poison body that can never parse is parked — retrying it forever would stall the stream
  # [ASSUMPTION: confidence=medium] A body that cannot be parsed is a deterministic (poison) failure routed to the dead-letter subject
  @task:TASK-RLY-005
  @negative
  Scenario: An episode whose body cannot be parsed is routed to the dead-letter subject
    Given a MemoryEpisodeV1 whose body is not parseable for its declared content format
    When the consumer receives the episode
    Then the episode should be routed to the dead-letter subject with a recorded reason
    And the consumer should continue processing other episodes

  # Why: An unknown payload type cannot be dispatched — registry has no silent fallback (FEAT-MEM-02 contract)
  @task:TASK-RLY-005
  @negative
  Scenario: A structured episode declaring an unknown payload type is parked
    Given a structured JSON episode declaring a payload type the registry does not know
    When the consumer receives the episode
    Then no record should be written
    And the episode should be routed to the dead-letter subject naming the unknown payload type

  # Why: A structured body missing a required field is a deterministic validation failure, never a write
  @task:TASK-RLY-005
  @negative
  Scenario: A structured episode that fails payload validation is parked without a write
    Given a structured JSON episode missing a field its payload type requires
    When the consumer receives the episode
    Then no record should be written
    And the episode should be routed to the dead-letter subject

  # Why: An unrecognized content format has no path — it must be parked, not guessed at
  # [ASSUMPTION: confidence=low] The only recognized content formats are json, markdown, and text
  @task:TASK-RLY-005
  @negative
  Scenario: An episode with an unrecognized content format is parked
    Given a MemoryEpisodeV1 whose content format is "yaml"
    When the consumer receives the episode
    Then no record or chunk should be created
    And the episode should be routed to the dead-letter subject

  # Why: Underscores-everywhere — a hyphenated project is rejected before any write, on both paths
  @task:TASK-RLY-005
  @negative
  Scenario: An episode whose project contains a hyphen is parked before any write
    Given a MemoryEpisodeV1 for project "guard-kit"
    When the consumer receives the episode
    Then no record or chunk should be created
    And the episode should be routed to the dead-letter subject

  # Why: Transient failures must be retried, never parked — distinguishing them from poison is the core ack/nak decision
  # [ASSUMPTION: confidence=medium] A transient downstream failure causes a negative-acknowledge and redelivery, not dead-lettering
  @task:TASK-RLY-005
  @negative
  Scenario: A transient downstream failure causes redelivery rather than dead-lettering
    Given the embedding service is temporarily unavailable
    When the consumer processes a markdown episode
    Then the episode should be negatively acknowledged for redelivery
    And the episode should not be sent to the dead-letter subject

  # ──────────────────────── Edge cases ───────────────────────────────

  # Why: AC — redelivery of an acked structured episode changes nothing (writer natural-key upsert is the ledger)
  @task:TASK-RLY-005
  @edge-case @regression
  Scenario: Redelivery of an already-stored structured episode changes nothing
    Given a structured episode that has already been processed and stored
    When the same episode is delivered again
    Then only one record should exist for that payload's natural key
    And the redelivery should leave the stored record unchanged

  # Why: AC — redelivery of an acked prose episode produces no duplicate chunks (episode_id keys are the ledger)
  # [ASSUMPTION: confidence=medium] Chunk identity is derived from the episode_id plus chunk position, making re-chunking idempotent
  @task:TASK-RLY-005
  @edge-case @regression
  Scenario: Redelivery of an already-chunked prose episode creates no duplicate chunks
    Given a markdown episode that has already been chunked and stored
    When the same episode is delivered again
    Then the chunk set for that episode should be identical to before
    And no duplicate chunk should be created

  # Why: AC — a poison episode is parked after the delivery limit and the consumer keeps going
  @task:TASK-RLY-006
  @edge-case @regression
  Scenario: A poison episode is parked and the consumer keeps processing the episodes behind it
    Given a poison episode at the head of the stream followed by valid episodes
    When the consumer works through the stream
    Then the poison episode should end up on the dead-letter subject
    And every valid episode behind it should be processed and acknowledged

  # Why: The at-least-once seam — a crash after commit but before ack must redeliver to an idempotent no-op
  @task:TASK-RLY-005
  @edge-case @regression
  Scenario: A crash after the write commits but before the ack results in an idempotent redelivery
    Given an episode whose write commits but whose acknowledgement is lost to a crash
    When the episode is redelivered after restart
    Then no second record or duplicate chunk should be created
    And the episode should then be acknowledged

  # Why: AC — no language model touches the ingestion path (the whole thesis, as an enforceable check)
  @task:TASK-RLY-005
  @edge-case @regression @negative
  Scenario: Ingesting episodes makes no language-model or chat-completion calls
    Given a batch of structured and prose episodes
    When the consumer ingests the entire batch
    Then no language-model or chat-completion request should be made on the write path

  # Why: Structured and prose episodes are independent — one path failing must not block the other
  @task:TASK-RLY-005
  @edge-case
  Scenario: A failing prose episode does not block structured episodes interleaved with it
    Given a stream interleaving a failing markdown episode with valid structured episodes
    When the consumer processes the stream
    Then the structured episodes should be stored and acknowledged
    And the failing markdown episode should be handled by its own ack or dead-letter decision

  # Why: Chunk-write atomicity — a mid-document failure must not leave a half-chunked episode behind
  # [ASSUMPTION: confidence=low] A prose episode's chunks are committed so that a partial failure leaves no incomplete chunk set for that episode_id
  @task:TASK-RLY-005
  @edge-case
  Scenario: A prose episode interrupted partway through chunking leaves no partial chunk set
    Given a markdown episode whose chunk writes fail partway through
    When the episode is redelivered and reprocessed
    Then the stored chunk set for that episode should be complete
    And no orphaned partial chunks should remain for that episode

  # ──────────────── Edge cases — security / injection ─────────────────

  # Why: Memory content is data, never instructions — hostile prose must round-trip inert through chunking
  @task:TASK-RLY-005
  @edge-case @negative
  Scenario: A prose episode containing injection-shaped text is chunked and stored verbatim and stays inert
    Given a markdown episode whose body contains database commands and prompt-injection text
    When the consumer chunks and stores the episode
    Then the stored chunks should contain that text byte-for-byte as written
    And no command in the content should be executed
    And no other record or namespace should be affected

  # Why: Chunk identity is derived data — delimiter or path text in episode metadata must not forge identity elsewhere
  @task:TASK-RLY-004
  @edge-case @negative
  Scenario: An episode whose identifiers carry delimiter or path text cannot forge a chunk identity in another namespace
    Given a markdown episode for project "guardkit" whose episode reference carries key-delimiter or path-shaped text
    When the consumer processes the episode
    Then every resulting chunk should be confined to the "guardkit" chunk namespace
    And no chunk should be written outside that project namespace

  # ──────────────────── Edge cases — concurrency ──────────────────────

  # Why: At-least-once delivery can race the same episode against itself — both deliveries must converge to one outcome
  @task:TASK-RLY-005
  @edge-case @regression
  Scenario: The same episode delivered twice concurrently converges to a single stored outcome
    Given the same episode delivered twice at the same time under at-least-once delivery
    When the consumer processes both deliveries concurrently
    Then exactly one record or one chunk set should exist for that episode
    And no duplicate should ever be created

  # Why: Concurrent episodes for one project must not cross-contaminate each other's writes
  @task:TASK-RLY-005
  @edge-case
  Scenario: Two different episodes for the same project processed concurrently write independently
    Given two different episodes for project "guardkit" arriving at the same time
    When the consumer processes both concurrently
    Then each episode should produce its own record or chunk set
    And neither episode's content should appear in the other's stored output

  # ─────────────── Edge cases — integration boundaries ────────────────

  # Why: Zero capture loss is the founding invariant — a store outage must redeliver, never silently drop in-flight work
  @task:TASK-RLY-006
  @edge-case @negative @regression
  Scenario: A store outage mid-batch redelivers in-flight episodes rather than losing them
    Given a batch of episodes being processed when the store becomes unreachable
    When the in-flight writes fail
    Then the affected episodes should be negatively acknowledged for redelivery
    And no in-flight episode should be acknowledged as stored
    And every episode should later be either stored or recorded on the dead-letter subject

  # Why: A wrong-dimension embedding must fail loudly, never persist a malformed chunk
  @task:TASK-RLY-004
  @edge-case @negative
  Scenario: An embedding with the wrong dimensions fails the chunk write and parks the episode
    Given the store is configured for its fixed embedding dimensions
    When the consumer stores a chunk whose embedding has a different number of dimensions
    Then the chunk write should fail with a dimension mismatch
    And no malformed chunk should be stored

===deterministic-writer summary===
# Feature Spec Summary: Deterministic Writer

**Stack**: python
**Generated**: 2026-06-13T10:20:27Z
**Scenarios**: 29 total (13 smoke, 4 regression)
**Assumptions**: 10 total (3 high / 5 medium / 2 low confidence)
**Review required**: Yes

## Scope

The deterministic writer (FEAT-MEM-03) turns a typed payload from the registry
(FEAT-MEM-02) into `AsyncPostgresStore` records with zero language-model calls.
It covers stable record identity (UUIDv5 from the natural key), content-hash
upsert semantics (same key + same content = no-op; same key + new content =
versioned update), declared supersession linking (mark predecessor
`superseded_by`, exclude from default retrieval), embed-on-write, and
per-project namespaces `("fleet_memory", project, payload_type)`. Idempotency
and supersession are the two test suites the build plan calls for; the
zero-LLM guarantee is expressed as an enforceable negative.

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 8 |
| Boundary conditions (@boundary) | 4 |
| Negative cases (@negative) | 9 |
| Edge cases (@edge-case) | 15 |

(Tags overlap: several scenarios carry both @edge-case and @negative, or
@boundary and @negative; the column counts every tag occurrence.)

## Deferred Items

None. All four proposal groups and the 6-scenario expansion group were accepted.

## Open Assumptions (low confidence)

These two require human verification before the spec is treated as settled
(REVIEW REQUIRED):

- **ASSUM-008** — Forward supersession: declaring a supersession of a
  not-yet-written key succeeds and is applied when that key later appears.
  Alternative design: reject the write, or drop the dangling link silently.
- **ASSUM-010** — Batch write behaviour: one record per distinct natural key.
  Partial-batch failure mode (all-or-nothing vs per-item) is unspecified.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Deterministic Writer" \
      --context features/deterministic-writer/deterministic-writer_summary.md

Note: `@task:<TASK-ID>` tags are intentionally absent — `/feature-plan`
Step 11 links scenarios to the tasks it creates.
Let me check the build plan docs for re-index/backfill context.

Bash Search build plan for re-index/backfill terms
IN
cd /Users/richardwoollcott/Projects/appmilla_github/fleet-memory; grep -niE "re-?index|backfill|seed module|corpus|fable|staging|review gate|nats-core|live relay|publish" docs/research/ideas/phase-core-build-plan.md docs/research/ideas/phase-core-scope.md 2>/dev/null | head -60

OUT
docs/research/ideas/phase-core-scope.md:5:## Status: **Phase CORE not started.** Repo initialized from `nats-asyncio-service` template 2026-06-12; slash-command capture hook wired same day. Fable 5 subscription window: ~10 days from 2026-06-12 — the one-time backfill (FEAT-MEM-07) and heavy planning sessions must land inside it.
docs/research/ideas/phase-core-scope.md:15:> A typed, deterministic memory store (Postgres + pgvector behind LangGraph `AsyncPostgresStore`), fed by the NATS episode relay and embedding with the always-on nomic endpoint, can replace Graphiti as the fleet's development-knowledge memory — with **zero LLM on the write path** for structured content, retrieval quality **≥ Graphiti** on real job-context queries, the **~28GB always-on extraction model retired**, and the **cloud fallback deleted** — built, re-indexed, and cut over inside the 10-day Fable 5 window.
docs/research/ideas/phase-core-scope.md:17:If true, `qwen-graphiti` leaves the preload permanently, the Gemini fallback path dies, the guardkit/graphiti fork stops mattering, and every fleet agent (including AWS-deployed ones) gets memory capture as a fire-and-forget NATS publish. If false at the retrieval-quality gate, the diagnosis (filter miss, embedding miss, missing relationship traversal) is recorded against the GROI framework and Graphiti unfreezes — the relay, schemas, and deterministic writer survive that outcome unchanged.
docs/research/ideas/phase-core-scope.md:27:| Migration is free by design | ADR-SP-007: markdown is authoritative, Graphiti was only an index. Replacement = re-index from source, not data rescue |
docs/research/ideas/phase-core-scope.md:28:| Fable 5 window | ~10 days of frontier capacity for planning sessions and the one-time unstructured-legacy backfill ("teacher funds its own replacement", executed literally) |
docs/research/ideas/phase-core-scope.md:30:The workload decomposition that makes the thesis credible: the majority of fleet memory writes are **structured at source** (ADRs, review reports, build outcomes, decision logs, seed modules — typed, keyed, versioned). Running those through LLM extraction was solving a problem we don't have. The genuinely unstructured slice (third-party docs, conversation capture) ships as chunk+embed with **no extraction at all** in this phase — raw episodes remain durably in the MEMORY stream, so LLM enrichment stays a future batch option, never a gate.
docs/research/ideas/phase-core-scope.md:37:| Slash-command capture hook → `docs/history/` (fine-tune corpus) | `.claude/hooks/capture_slash_command.py` | ✅ wired 2026-06-12, verbatim from specialist-agent |
docs/research/ideas/phase-core-scope.md:40:| nats-core schema/client package pattern (`pip install git+ssh`) | nats-core | ✅ live; memory schemas are a cross-repo deliverable |
docs/research/ideas/phase-core-scope.md:42:| Authoritative markdown corpus: guardkit 22 seed modules, ADRs, review reports, task outcomes | guardkit et al. | ✅ on disk — the re-index source |
docs/research/ideas/phase-core-scope.md:57:| FEAT-MEM-07 | Re-index + Fable backfill — guardkit seeds/ADRs through the writer from markdown; one-time Fable 5 job structuring genuinely unstructured legacy docs into typed payloads | Populates the store from authoritative source (ADR-SP-007 made this free). The backfill is the only frontier-model job in the phase — authored once, inside the window, never needed again. |
docs/research/ideas/phase-core-scope.md:66:2. **Zero-LLM structured writes.** 100% of typed-payload writes complete with no LLM call, measured at the serving layer (no `qwen-graphiti` traffic during re-index of structured content).
docs/research/ideas/phase-core-scope.md:67:3. **Zero capture loss.** Stream-vs-store audit over the soak: every `MemoryEpisodeV1` published is either ingested or in DLQ with a recorded reason. No silent losses — the failure mode that started all of this.
docs/research/ideas/phase-core-scope.md:70:6. **Re-index is cheap.** Full guardkit re-index from markdown completes in minutes, not hours, and is idempotently re-runnable — proving the recovery/migration story.
docs/research/ideas/phase-core-scope.md:77:| Trace proxy / MEMORY_TRACES (relay D8/P5) | Its purpose was a training corpus for a distilled *extraction* model; with extraction off the write path, it's demoted to optional. Revisit if extraction returns. |
docs/research/ideas/phase-core-scope.md:83:| jarvis/forge/specialist-agent publisher integrations | The nats-core publisher makes these one-call adds; guardkit is the exemplar in-window, fleet rollout follows. |
docs/research/ideas/phase-core-scope.md:88:- **DECISION-DF-001.** No cloud API on the dark-factory critical path. Fable 5 is used for *authoring* (planning sessions, one-time backfill content) — never wired into runtime ingestion or retrieval.
docs/research/ideas/phase-core-scope.md:89:- **ADR-SP-007 carried forward.** Markdown stays authoritative; the store is an index. Any "fix the data" instinct routes to fixing the source document and re-indexing.
docs/research/ideas/phase-core-scope.md:106:| Fable 5 window | 🕐 ~10 days from 2026-06-12 |
docs/research/ideas/phase-core-build-plan.md:6:## Prerequisites: repo initialized from `nats-asyncio-service` (done 2026-06-12); capture hook wired (done); Fable 5 window open (~10 days from 2026-06-12); always-on nomic-embed at llama-swap :9000; NATS JetStream live.
docs/research/ideas/phase-core-build-plan.md:17:Graphiti is being replaced as the fleet's development-knowledge memory. The full case is in the scope doc; the operational summary: TASK-REV-GROI found 0/10 consumption paths proven high-value; the write path costs ~28GB always-on (`qwen-graphiti`) after every consolidation route failed (findings §9.5–§9.8); the cloud fallback cost £30 in one weekend; and ADR-SP-007 (markdown authoritative) makes replacement a re-index rather than a migration. The Memory Relay (nats-infrastructure) provides durable LLM-free capture; this repo provides the store, the deterministic writer, retrieval, and the MCP surface.
docs/research/ideas/phase-core-build-plan.md:23:| nats-core | `MemoryEpisodeV1` envelope schema + publisher helper | Relay P1 (one small feature) |
docs/research/ideas/phase-core-build-plan.md:26:| guardkit | Publisher integration + read-path cutover | Coordinated rows inside FEAT-MEM-07/08 |
docs/research/ideas/phase-core-build-plan.md:46:| FEAT-MEM-07 | Re-index + Fable backfill | Not started | — |
docs/research/ideas/phase-core-build-plan.md:52:- DECISION-DF-001: Fable for authoring only; zero cloud in runtime paths.
docs/research/ideas/phase-core-build-plan.md:53:- ADR-SP-007: store is an index; fixes go to source markdown + re-index.
docs/research/ideas/phase-core-build-plan.md:72:| Durable shared Postgres | Synology NAS, Container Manager project (compose + notes in `deploy/nas/`) | Re-index target (07), MCP server, relay consumer, soak | Volume on a backed-up shared folder; port 5432 exposed to LAN/Tailscale only; reachable from the Mac during dev as `FLEET_MEMORY_PG_DSN` pointing at the NAS |
docs/research/ideas/phase-core-build-plan.md:124:**Status:** Spec'd 2026-06-13 via `/feature-spec` → `features/deterministic-writer/` (29 scenarios; 10 assumptions — 2 low-confidence flagged REVIEW REQUIRED: forward supersession of a not-yet-written key (ASSUM-008), batch-write / partial-batch failure mode (ASSUM-010)). Zero-LLM guarantee captured as an enforceable negative scenario; idempotency, supersession, and re-index-idempotency suites covered. Uncommitted on `main`. `/feature-plan` next.
docs/research/ideas/phase-core-build-plan.md:140:- [ ] Write throughput: full guardkit seed corpus in < 5 minutes (measured in 07)
docs/research/ideas/phase-core-build-plan.md:149:/feature-spec "Relay integration: FastStream durable consumer on MEMORY stream consuming MemoryEpisodeV1 from nats-core; structured_json episodes dispatch through payload registry to deterministic writer; markdown/text episodes chunk+embed with heading-aware chunking; ack/nak/DLQ per relay scope; TestNatsBroker test suite incl. poison message and redelivery idempotency"
docs/research/ideas/phase-core-build-plan.md:155:- [ ] Publish 3 structured + 2 markdown episodes via TestNatsBroker → 3 typed records + N chunks
docs/research/ideas/phase-core-build-plan.md:176:- [ ] p95 search latency < 200ms against the re-indexed corpus (local network)
docs/research/ideas/phase-core-build-plan.md:195:## FEAT-MEM-07: Re-index + Fable Backfill
docs/research/ideas/phase-core-build-plan.md:197:Two parts. (a) Re-index script: walk guardkit's authoritative markdown (seed modules, ADRs, review reports, completed-task outcomes), parse to typed payloads (deterministic parsers — front-matter and house formats are regular), publish via nats-core helper (exercising the full relay path). (b) Fable backfill: one-time, window-bound job where Fable 5 reads the genuinely unstructured legacy docs and authors typed payloads for human review before publishing — output is reviewed markdown/JSON in the repo, so the result is re-runnable forever without any frontier model.
docs/research/ideas/phase-core-build-plan.md:202:/feature-spec "Re-index pipeline: deterministic markdown-to-typed-payload parsers for guardkit seed modules, ADRs, review reports and task outcomes, publishing via nats-core MemoryEpisodeV1 through the live relay; idempotent full-corpus runs; backfill staging area for Fable-authored payloads with human review gate before publish"
docs/research/ideas/phase-core-build-plan.md:208:- [ ] Full guardkit re-index < 5 min, zero LLM calls, idempotent on second run
docs/research/ideas/phase-core-build-plan.md:209:- [ ] Backfill payloads land in `backfill/staging/` and publish only after review flag
docs/research/ideas/phase-core-build-plan.md:211:- [ ] Probe-set parity report generated against this corpus (feeds criterion 1)
docs/research/ideas/phase-core-build-plan.md:234:## Build Sequence (Fable window: ~2026-06-12 → ~2026-06-21; half-days assumed around Evri)
docs/research/ideas/phase-core-build-plan.md:238:| 1 (Fri 12) | This pair; ~~`/feature-spec` + `/feature-plan` FEAT-MEM-01~~ ✅; relay P1 spec in nats-core (on instruction) |
docs/research/ideas/phase-core-build-plan.md:241:| 5 (Tue 16) | FEAT-MEM-04 relay consumer; first end-to-end publish→store |
docs/research/ideas/phase-core-build-plan.md:243:| 7 (Thu 18) | FEAT-MEM-06 MCP; FEAT-MEM-07 re-index parsers |
docs/research/ideas/phase-core-build-plan.md:244:| 8 (Fri 19) | FEAT-MEM-07 full re-index + **Fable backfill day** (the window-critical task) |
docs/research/ideas/phase-core-build-plan.md:248:**Cut lines if the window compresses:** FEAT-MEM-06 (MCP) and FEAT-MEM-08 can slip past the window — they don't need Fable. FEAT-MEM-07's backfill is the only deliverable that genuinely expires with the subscription; protect Day 8.
docs/research/ideas/phase-core-build-plan.md:269:| OD-3 | guardkit client mechanism for 08 (thin HTTP/lib client vs MCP) | Thin library client (import via git+ssh like nats-core); MCP stays a Desktop surface | FEAT-MEM-08 |
docs/research/ideas/phase-core-build-plan.md:278:| Fable window closes before Day 8 backfill | Backfill is staged + reviewable; worst case the unstructured legacy slice ships chunk-only (already the v1 contract) and typed backfill happens later with a local model |
docs/research/ideas/phase-core-build-plan.md:280:| NAS Postgres performance under embed-heavy re-index | Embeddings computed GB10-side via llama-swap; Postgres only stores; if insert throughput disappoints, batch upserts (writer already batches) |
Let me read the full FEAT-MEM-07 section and the nats-core publisher helper details.

Bash Read FEAT-MEM-07 detail section
IN
cd /Users/richardwoollcott/Projects/appmilla_github/fleet-memory; sed -n '195,232p' docs/research/ideas/phase-core-build-plan.md

OUT
## FEAT-MEM-07: Re-index + Fable Backfill

Two parts. (a) Re-index script: walk guardkit's authoritative markdown (seed modules, ADRs, review reports, completed-task outcomes), parse to typed payloads (deterministic parsers — front-matter and house formats are regular), publish via nats-core helper (exercising the full relay path). (b) Fable backfill: one-time, window-bound job where Fable 5 reads the genuinely unstructured legacy docs and authors typed payloads for human review before publishing — output is reviewed markdown/JSON in the repo, so the result is re-runnable forever without any frontier model.

### Spec & Plan Commands

```
/feature-spec "Re-index pipeline: deterministic markdown-to-typed-payload parsers for guardkit seed modules, ADRs, review reports and task outcomes, publishing via nats-core MemoryEpisodeV1 through the live relay; idempotent full-corpus runs; backfill staging area for Fable-authored payloads with human review gate before publish"
/feature-plan FEAT-XXXX
```

### Acceptance Criteria

- [ ] Full guardkit re-index < 5 min, zero LLM calls, idempotent on second run
- [ ] Backfill payloads land in `backfill/staging/` and publish only after review flag
- [ ] Stream-vs-store audit script reports 100% accounted (ingested or DLQ'd)
- [ ] Probe-set parity report generated against this corpus (feeds criterion 1)

## FEAT-MEM-08: GuardKit Read-Path Cutover (cross-repo)

GuardKit's coach context builder, feature-plan context, and CLI retrieval point at fleet-memory's retrieval API (thin client or MCP). The GROI anti-criterion: reads must demonstrably fire in real pipeline runs. Coordinated guardkit tasks created on explicit instruction when 05+07 land.

### Acceptance Criteria

- [ ] One real `/feature-plan` and one AutoBuild run show fleet-memory retrieval in history files
- [ ] Graphiti client paths in guardkit behind a feature flag, default off

## FEAT-MEM-09: Cutover + Decommission Runbook

`docs/runbooks/RUNBOOK-graphiti-cutover.md` in house style (phased bash, PASS/FAIL gates, decision-gate table, rollback commands, explicit what-NOT-to-do): qwen-graphiti out of always-on preload; Gemini fallback blocks deleted from all `graphiti.yaml`s; Graphiti/FalkorDB frozen read-only for the soak; steady-state memory measured; findings doc §9.x entry in guardkit; archive decision after soak.

### Acceptance Criteria

- [ ] ~28GB steady-state reduction measured and recorded
- [ ] £0 cloud on memory path (config grep proves no Gemini fallback remains)
- [ ] Rollback path tested on paper: unfreeze Graphiti + flag flip restores old reads

---
Context loaded: stack=python, 7 payload-type models found, 6 existing .feature files, 2 ADRs referenced (ADR-SP-007 markdown-authoritative, DECISION-DF-001 Fable-authoring-only), FEAT-MEM-07 build-plan section read.

This feature is FEAT-MEM-07: Re-index + Fable Backfill. It depends on the deterministic writer (FEAT-MEM-03), typed payload registry (FEAT-MEM-02), and relay (FEAT-MEM-04), all of which already exist. The re-index publishes through that live path; idempotency and versioning are enforced downstream by the writer's content-hash upsert.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC PROPOSAL: Re-index Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


Feature: Re-index Pipeline
  As a fleet-memory operator
  I want to re-index guardkit's authoritative markdown corpus into typed payloads published through the live relay, with deterministic parsers and a reviewed staging gate for frontier-authored backfill
  So that the store can be rebuilt from source at any time — cheaply, idempotently, and with no language model on the publish path

  Background:
    Given the guardkit markdown corpus is available on disk with seed modules, ADRs, review reports, and completed-task outcomes
    And the publisher helper can publish a memory episode onto the memory stream
    And the live relay is consuming the memory stream into the store
━━ GROUP A: Key Examples (8 scenarios) ━━


  # Why: Core path — a seed module document parses to its canonical typed payload and is published
  @key-example @smoke
  Scenario: A seed module document is parsed into a seed-module payload and published
    Given a seed module document in the corpus
    When the re-index pipeline processes the corpus
    Then a seed-module payload should be published for that document
    And the published episode should identify the source document

  # Why: ADRs carry decision text and status — the deterministic parser maps front-matter to typed fields
  @key-example @smoke
  Scenario: An ADR document is parsed into an ADR payload carrying its decision and status
    Given an ADR document in the corpus with a decision and a status
    When the re-index pipeline processes the corpus
    Then an ADR payload should be published carrying that decision and status

  # Why: Review reports carry a verdict — confirms the house-format parser for this type
  @key-example
  Scenario: A review report document is parsed into a review-report payload carrying its verdict
    Given a review report document in the corpus with a verdict
    When the re-index pipeline processes the corpus
    Then a review-report payload should be published carrying that verdict

  # Why: Completed-task outcomes map to build-outcome payloads
  @key-example
  Scenario: A completed-task outcome document is parsed into a build-outcome payload
    Given a completed-task outcome document in the corpus
    When the re-index pipeline processes the corpus
    Then a build-outcome payload should be published for that document

  # Why: The headline AC — a full-corpus run publishes every recognized document as a typed episode
  @key-example @smoke
  Scenario: A full-corpus run publishes a typed episode for every recognized document
    Given a corpus containing seed modules, ADRs, review reports, and task outcomes
    When the re-index pipeline runs over the whole corpus
    Then every recognized document should be published as a typed memory episode
    And each episode should declare the payload type matching its document kind

  # Why: Routing key — published episodes are structured so the relay dispatches them to the deterministic writer, not the chunker
  @key-example @smoke
  Scenario: Published episodes are structured so the relay routes them to the deterministic writer
    Given a recognized document parsed into a typed payload
    When the pipeline publishes the episode
    Then the episode should be marked as structured content for its payload type
    And the relay should route it to the deterministic writer rather than the prose path

  # Why: Each document kind has exactly one canonical payload type — the parser-to-type mapping is explicit and reviewable
  @key-example
  Scenario Outline: Each corpus document kind maps to its canonical payload type
    Given a "<document kind>" document in the corpus
    When the re-index pipeline processes the corpus
    Then it should be published as a "<payload type>" payload

    Examples:
      | document kind        | payload type  |
      | seed module          | seed_module   |
      | ADR                  | adr           |
      | review report        | review_report |
      | completed-task outcome | build_outcome |

  # Why: The thesis — re-indexing structured content makes no language-model call (DECISION-DF-001, zero-LLM write path)
  @key-example @smoke @regression
  Scenario: A full re-index run makes no language-model call
    Given a corpus of recognized documents
    When the re-index pipeline runs over the whole corpus
    Then no language-model or chat-completion request should be made during parsing or publishing
━━ GROUP B: Boundary Conditions (5 scenarios) ━━


  # Why: Empty-corpus boundary — a run over nothing completes cleanly and publishes nothing
  @boundary
  Scenario: A run over an empty corpus publishes nothing and completes cleanly
    Given a corpus directory containing no documents
    When the re-index pipeline runs
    Then no episode should be published
    And the run should complete successfully

  # Why: Single-document boundary — the smallest non-empty corpus
  @boundary
  Scenario: A run over a corpus of one document publishes exactly one episode
    Given a corpus containing exactly one recognized document
    When the re-index pipeline runs
    Then exactly one episode should be published

  # Why: Just-inside boundary — a document carrying exactly the fields its payload type requires is parsed and published
  @boundary
  Scenario: A document carrying exactly the required fields for its type is published
    Given an ADR document carrying exactly a decision and a status and nothing more
    When the re-index pipeline processes the corpus
    Then an ADR payload should be published for that document

  # Why: Just-outside boundary — a document missing a field its payload type requires is not published
  @boundary @negative
  Scenario: A document missing a field its payload type requires is not published
    Given an ADR document with no status field
    When the re-index pipeline processes the corpus
    Then no payload should be published for that document
    And the run should report the document as unparseable with a reason

  # Why: Performance boundary — the full guardkit corpus re-indexes within the time budget (AC)
  # [ASSUMPTION: confidence=high] A full guardkit re-index completes in under 5 minutes
  @boundary
  Scenario: A full guardkit corpus re-index completes within the time budget
    Given the full guardkit markdown corpus
    When the re-index pipeline runs over the whole corpus
    Then the run should complete in under five minutes
━━ GROUP C: Negative Cases (5 scenarios) ━━


  # Why: Malformed front-matter is a deterministic parse failure — reported and skipped, never silently dropped
  @negative
  Scenario: A document with malformed front-matter is reported and skipped
    Given a document whose front-matter cannot be parsed
    When the re-index pipeline processes the corpus
    Then no episode should be published for that document
    And the run should record the document as a parse failure with a reason

  # Why: An unrecognized document kind has no parser — it is accounted for, not guessed at or dropped
  @negative
  Scenario: A document matching no known parser is recorded as unrecognized
    Given a document that matches none of the known document kinds
    When the re-index pipeline processes the corpus
    Then no episode should be published for that document
    And the run should record the document as unrecognized

  # Why: The review gate is the whole point of staging — an unreviewed backfill payload must never reach the relay
  @negative
  Scenario: An unreviewed backfill payload is not published
    Given a backfill payload in the staging area that has not been marked as reviewed
    When the re-index pipeline runs
    Then that backfill payload should not be published

  # Why: DECISION-DF-001 — no cloud or frontier model is invoked on the publish path, only during offline authoring
  @negative
  Scenario: The re-index pipeline invokes no cloud or frontier model
    Given a corpus of recognized documents and a staging area of reviewed backfill payloads
    When the re-index pipeline runs
    Then no cloud or frontier-model request should be made by the pipeline

  # Why: One bad document must not abort the whole corpus run — the rest still publish
  @negative
  Scenario: A single unparseable document does not abort the corpus run
    Given a corpus where one document has malformed front-matter and the rest are valid
    When the re-index pipeline runs over the whole corpus
    Then every valid document should be published
    And the run should report the one unparseable document
━━ GROUP D: Edge Cases (6 scenarios) ━━


  # Why: The headline AC — re-running over an unchanged corpus changes nothing in the store (downstream content-hash upsert)
  @edge-case @regression
  Scenario: A second run over an unchanged corpus leaves the store unchanged
    Given a corpus that has already been fully re-indexed
    When the re-index pipeline runs again with no source documents changed
    Then no stored record should be created or modified

  # Why: ADR-SP-007 — fixing a source document and re-indexing updates the record, never duplicates it
  @edge-case @regression
  Scenario: Re-indexing after editing a source document updates its record rather than duplicating it
    Given a document that has already been re-indexed
    And that document's content has since changed
    When the re-index pipeline runs again
    Then the record for that document should be updated to the new content
    And no duplicate record should exist for that document

  # Why: A run interrupted partway is safely resumable — already-published episodes are durable, a re-run completes the rest
  @edge-case
  Scenario: A run interrupted partway through can be safely re-run to completion
    Given a re-index run that is interrupted after publishing some but not all documents
    When the re-index pipeline is run again over the whole corpus
    Then every document should end up published exactly once in the store
    And no duplicate record should result from the documents published before the interruption

  # Why: The backfill happy path — a reviewed staged payload publishes through the same relay path as deterministic re-index
  @edge-case
  Scenario: A reviewed backfill payload is published on the next run
    Given a backfill payload in the staging area that has been marked as reviewed
    When the re-index pipeline runs
    Then that backfill payload should be published through the relay
    And it should be stored as a typed record like any deterministically parsed payload

  # Why: Stream-vs-store audit (AC) — after a run, every published episode is accounted for as ingested or dead-lettered
  @edge-case
  Scenario: After a run every published episode is accounted for as ingested or dead-lettered
    Given a completed full-corpus re-index run
    When the published episodes are audited against the store
    Then every published episode should be either stored or recorded on the dead-letter subject
    And no published episode should be unaccounted for

  # Why: Idempotency at the publish layer — re-publishing the same parsed document twice yields a single stored record
  @edge-case @regression
  Scenario: Publishing the same parsed document twice yields a single stored record
    Given a document parsed into a typed payload
    When the same payload is published twice through the relay
    Then exactly one record should exist for that document's natural key
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: 24 scenarios across 4 groups
Inferred assumptions: 5 (will be resolved in Phase 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURATION: Review each group
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For each group, you may:

[A] Accept  — include all scenarios as-is
[R] Reject  — exclude the group
[M] Modify  — accept but specify changes (provide inline)
[+] Add     — accept and add scenarios you describe
[?] Defer   — mark for future specification; excluded from output

Fast path: type "A A A A" to accept all four groups at once.


GROUP A — Key Examples (8 scenarios):        _
GROUP B — Boundary Conditions (5 scenarios): _
GROUP C — Negative Cases (5 scenarios):      _
GROUP D — Edge Cases (6 scenarios):          _
After curation I'll offer Phase 4 (edge-case expansion: security / concurrency / integration) and then Phase 5 (assumption resolution) — the 5 inferred assumptions are the 5-minute time budget, the review-gate mechanism, the backfill/staging/ location, unrecognized-document handling, and content-format routing.

How would you like to curate the four groups?

phase-core-build-plan.md
A A A A
All four groups accepted. Now Phase 4.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDGE CASE EXPANSION (optional)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

I've identified 6 additional scenarios covering security, concurrency, and integration boundaries specific to the re-index pipeline:

Security (3):

A source document whose body contains injection-shaped text (SQL / prompt-injection) is published verbatim as payload data and stays inert
The corpus walk cannot escape the corpus root via a path-traversal filename (../../etc/...)
A staged backfill payload cannot self-certify — the review flag is operator-controlled, so a file claiming to be reviewed inside its own content is still gated
Concurrency (1):

Two re-index runs started at the same time converge to a single stored outcome (no duplicates)
Integration boundaries (2):

When the relay or store is unavailable mid-run, the run reports failure and no document is silently lost — the run is safely resumable
Backfill payloads publish through the same relay path and deterministic writer as parsed documents (single write path, byte-identical handling)

[Y] Yes    — show and curate all 6 (A/R/M/+/? actions)
[S] Sample — show 2 examples, then decide
[N] No     — skip to Phase 5
Your choice [Y/S/N]?

Y
Here are the 6 expansion scenarios for curation.

━━ SECURITY (3 scenarios) ━━


  # Why: Memory content is data, never instructions — hostile prose must round-trip inert through the pipeline
  @edge-case @negative
  Scenario: A document whose body contains injection-shaped text is published verbatim and stays inert
    Given a document whose body contains database commands and prompt-injection text
    When the re-index pipeline parses and publishes the document
    Then the published payload should contain that text byte-for-byte as written
    And no command in the content should be executed during parsing or publishing

  # Why: The corpus walk must stay inside its root — a crafted path must not let the pipeline read outside the corpus
  @edge-case @negative
  Scenario: A path-traversal filename in the corpus cannot make the pipeline read outside the corpus root
    Given a corpus entry whose name contains path-traversal segments
    When the re-index pipeline walks the corpus
    Then only documents within the corpus root should be read
    And no file outside the corpus root should be published

  # Why: The review gate is operator-controlled — a payload cannot mark itself reviewed to bypass the gate
  @edge-case @negative
  Scenario: A backfill payload that claims to be reviewed within its own content is still gated
    Given a staged backfill payload whose own content asserts that it has been reviewed
    And no operator-controlled review marker exists for that payload
    When the re-index pipeline runs
    Then that backfill payload should not be published
━━ CONCURRENCY (1 scenario) ━━


  # Why: Two operators (or a retry overlapping the original) must not double the corpus
  @edge-case @regression
  Scenario: Two re-index runs started at the same time converge to a single stored outcome
    Given two re-index runs over the same corpus started at the same time
    When both runs publish their episodes through the relay
    Then exactly one record should exist for each document's natural key
    And no duplicate record should be created by the overlapping runs
━━ INTEGRATION BOUNDARIES (2 scenarios) ━━


  # Why: Zero capture loss — a relay or store outage mid-run must surface as failure, never a silent partial run
  @edge-case @negative @regression
  Scenario: A relay or store outage mid-run fails loudly and loses no document
    Given a re-index run in progress when the relay becomes unreachable
    When the in-flight publishes fail
    Then the run should report failure with the affected documents named
    And no document should be silently skipped
    And re-running the pipeline should publish every document that did not reach the store

  # Why: Single write path — staged backfill is handled byte-identically to deterministic re-index, no second code path
  @edge-case
  Scenario: Reviewed backfill payloads publish through the same relay path as deterministically parsed documents
    Given a corpus of recognized documents and a reviewed backfill payload in staging
    When the re-index pipeline runs
    Then both the parsed documents and the reviewed backfill payload should be published through the same relay path
    And both should be stored by the same deterministic writer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Curate these the same way (A/R/M/+/? — or just A to accept all 6):


SECURITY (3):              _
CONCURRENCY (1):           _
INTEGRATION (2):           _
A
All 6 accepted (30 scenarios total). Now Phase 5.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSUMPTION RESOLUTION (5 items)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Press Enter to accept each default, or type the actual value.


[1] Full re-index time budget
    Proposed: under 5 minutes   Confidence: high
    Basis: FEAT-MEM-07 acceptance criterion + build-plan throughput gate (< 5 min)
    Accept or enter value: _

[2] Backfill staging location
    Proposed: backfill/staging/   Confidence: high
    Basis: FEAT-MEM-07 AC ("Backfill payloads land in backfill/staging/")
    Accept or enter value: _

[3] Review-gate mechanism
    Proposed: an operator-controlled per-payload review marker (a file/flag outside the payload content)   Confidence: medium
    Basis: AC says "publish only after review flag"; the exact marker form is not specified
    Accept or enter value: _

[4] Unrecognized-document handling
    Proposed: skipped and recorded in the run report (not published, not aborted)   Confidence: medium
    Basis: "no silent losses" invariant; build plan doesn't state skip-vs-park for the publisher side
    Accept or enter value: _

[5] Structured-content routing marker
    Proposed: episodes published with content_format "json" and an explicit payload_type   Confidence: high
    Basis: relay schema (MemoryEpisodeV1) + relay service routing — json + payload_type dispatches to the deterministic writer
    Accept or enter value: _
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Respond per item (e.g. 1: accept, 2: accept, 3: a marker file named .reviewed alongside the payload, 4: accept, 5: accept), or accept all to take every default.

accept all
All assumptions accepted. Phase 6: writing files.

Write re-index-pipeline.feature
288 lines
# Generated by /feature-spec
# Feature: Re-index Pipeline (FEAT-MEM-07)
# Stack: python
# Assumptions: 5 (see re-index-pipeline_assumptions.yaml)
# Generated: 2026-06-13T20:05:00Z
#
# Context sources: docs/research/ideas/phase-core-build-plan.md (FEAT-MEM-07),
# docs/research/ideas/phase-core-scope.md, src/fleet_memory/relay/schema.py,
# src/fleet_memory/relay/service.py, src/fleet_memory/payloads/models.py,
# src/fleet_memory/payloads/registry.py, features/relay-integration/relay-integration.feature,
# features/deterministic-writer/deterministic-writer.feature
#
# The re-index pipeline PUBLISHES through the live relay path established by
# FEAT-MEM-04 (relay) into the FEAT-MEM-03 deterministic writer. Idempotency,
# versioned upsert, and natural-key dedup are enforced DOWNSTREAM by the writer's
# content-hash upsert; the pipeline's job is deterministic parsing, faithful
# publishing, and gating frontier-authored backfill behind a human review marker.
#
# Governing decisions: ADR-SP-007 (markdown is authoritative; the store is an index;
# fixes route to source + re-index) and DECISION-DF-001 (Fable for offline authoring
# only; zero cloud/frontier model on any runtime publish path).

@re-index-pipeline
Feature: Re-index Pipeline
  As a fleet-memory operator
  I want to re-index guardkit's authoritative markdown corpus into typed payloads published through the live relay, with deterministic parsers and a reviewed staging gate for frontier-authored backfill
  So that the store can be rebuilt from source at any time — cheaply, idempotently, and with no language model on the publish path

  Background:
    Given the guardkit markdown corpus is available on disk with seed modules, ADRs, review reports, and completed-task outcomes
    And the publisher helper can publish a memory episode onto the memory stream
    And the live relay is consuming the memory stream into the store

  # ───────────────────────── Key examples ────────────────────────────

  # Why: Core path — a seed module document parses to its canonical typed payload and is published
  @key-example @smoke
  Scenario: A seed module document is parsed into a seed-module payload and published
    Given a seed module document in the corpus
    When the re-index pipeline processes the corpus
    Then a seed-module payload should be published for that document
    And the published episode should identify the source document

  # Why: ADRs carry decision text and status — the deterministic parser maps front-matter to typed fields
  @key-example @smoke
  Scenario: An ADR document is parsed into an ADR payload carrying its decision and status
    Given an ADR document in the corpus with a decision and a status
    When the re-index pipeline processes the corpus
    Then an ADR payload should be published carrying that decision and status

  # Why: Review reports carry a verdict — confirms the house-format parser for this type
  @key-example
  Scenario: A review report document is parsed into a review-report payload carrying its verdict
    Given a review report document in the corpus with a verdict
    When the re-index pipeline processes the corpus
    Then a review-report payload should be published carrying that verdict

  # Why: Completed-task outcomes map to build-outcome payloads
  @key-example
  Scenario: A completed-task outcome document is parsed into a build-outcome payload
    Given a completed-task outcome document in the corpus
    When the re-index pipeline processes the corpus
    Then a build-outcome payload should be published for that document

  # Why: The headline AC — a full-corpus run publishes every recognized document as a typed episode
  @key-example @smoke
  Scenario: A full-corpus run publishes a typed episode for every recognized document
    Given a corpus containing seed modules, ADRs, review reports, and task outcomes
    When the re-index pipeline runs over the whole corpus
    Then every recognized document should be published as a typed memory episode
    And each episode should declare the payload type matching its document kind

  # Why: Routing key — published episodes are structured so the relay dispatches them to the writer, not the chunker
  # [ASSUMPTION: confidence=high] Structured episodes are published with content format "json" and an explicit payload type so the relay routes them to the deterministic writer
  @key-example @smoke
  Scenario: Published episodes are structured so the relay routes them to the deterministic writer
    Given a recognized document parsed into a typed payload
    When the pipeline publishes the episode
    Then the episode should be marked as structured content for its payload type
    And the relay should route it to the deterministic writer rather than the prose path

  # Why: Each document kind has exactly one canonical payload type — the parser-to-type mapping is explicit and reviewable
  @key-example
  Scenario Outline: Each corpus document kind maps to its canonical payload type
    Given a "<document kind>" document in the corpus
    When the re-index pipeline processes the corpus
    Then it should be published as a "<payload type>" payload

    Examples:
      | document kind          | payload type  |
      | seed module            | seed_module   |
      | ADR                    | adr           |
      | review report          | review_report |
      | completed-task outcome | build_outcome |

  # Why: The thesis — re-indexing structured content makes no language-model call (DECISION-DF-001, zero-LLM write path)
  @key-example @smoke @regression
  Scenario: A full re-index run makes no language-model call
    Given a corpus of recognized documents
    When the re-index pipeline runs over the whole corpus
    Then no language-model or chat-completion request should be made during parsing or publishing

  # ───────────────────── Boundary conditions ─────────────────────────

  # Why: Empty-corpus boundary — a run over nothing completes cleanly and publishes nothing
  @boundary
  Scenario: A run over an empty corpus publishes nothing and completes cleanly
    Given a corpus directory containing no documents
    When the re-index pipeline runs
    Then no episode should be published
    And the run should complete successfully

  # Why: Single-document boundary — the smallest non-empty corpus
  @boundary
  Scenario: A run over a corpus of one document publishes exactly one episode
    Given a corpus containing exactly one recognized document
    When the re-index pipeline runs
    Then exactly one episode should be published

  # Why: Just-inside boundary — a document carrying exactly the fields its payload type requires is parsed and published
  @boundary
  Scenario: A document carrying exactly the required fields for its type is published
    Given an ADR document carrying exactly a decision and a status and nothing more
    When the re-index pipeline processes the corpus
    Then an ADR payload should be published for that document

  # Why: Just-outside boundary — a document missing a field its payload type requires is not published
  @boundary @negative
  Scenario: A document missing a field its payload type requires is not published
    Given an ADR document with no status field
    When the re-index pipeline processes the corpus
    Then no payload should be published for that document
    And the run should report the document as unparseable with a reason

  # Why: Performance boundary — the full guardkit corpus re-indexes within the time budget (AC)
  # [ASSUMPTION: confidence=high] A full guardkit re-index completes in under 5 minutes
  @boundary
  Scenario: A full guardkit corpus re-index completes within the time budget
    Given the full guardkit markdown corpus
    When the re-index pipeline runs over the whole corpus
    Then the run should complete in under five minutes

  # ─────────────────────── Negative cases ────────────────────────────

  # Why: Malformed front-matter is a deterministic parse failure — reported and skipped, never silently dropped
  @negative
  Scenario: A document with malformed front-matter is reported and skipped
    Given a document whose front-matter cannot be parsed
    When the re-index pipeline processes the corpus
    Then no episode should be published for that document
    And the run should record the document as a parse failure with a reason

  # Why: An unrecognized document kind has no parser — it is accounted for, not guessed at or dropped
  # [ASSUMPTION: confidence=medium] A document matching no known parser is skipped and recorded in the run report, not published and not aborting the run
  @negative
  Scenario: A document matching no known parser is recorded as unrecognized
    Given a document that matches none of the known document kinds
    When the re-index pipeline processes the corpus
    Then no episode should be published for that document
    And the run should record the document as unrecognized

  # Why: The review gate is the whole point of staging — an unreviewed backfill payload must never reach the relay
  # [ASSUMPTION: confidence=medium] A backfill payload is published only when an operator-controlled review marker, held outside the payload content, is present
  @negative
  Scenario: An unreviewed backfill payload is not published
    Given a backfill payload in the staging area that has not been marked as reviewed
    When the re-index pipeline runs
    Then that backfill payload should not be published

  # Why: DECISION-DF-001 — no cloud or frontier model is invoked on the publish path, only during offline authoring
  @negative
  Scenario: The re-index pipeline invokes no cloud or frontier model
    Given a corpus of recognized documents and a staging area of reviewed backfill payloads
    When the re-index pipeline runs
    Then no cloud or frontier-model request should be made by the pipeline

  # Why: One bad document must not abort the whole corpus run — the rest still publish
  @negative
  Scenario: A single unparseable document does not abort the corpus run
    Given a corpus where one document has malformed front-matter and the rest are valid
    When the re-index pipeline runs over the whole corpus
    Then every valid document should be published
    And the run should report the one unparseable document

  # ──────────────────────── Edge cases ───────────────────────────────

  # Why: The headline AC — re-running over an unchanged corpus changes nothing in the store (downstream content-hash upsert)
  @edge-case @regression
  Scenario: A second run over an unchanged corpus leaves the store unchanged
    Given a corpus that has already been fully re-indexed
    When the re-index pipeline runs again with no source documents changed
    Then no stored record should be created or modified

  # Why: ADR-SP-007 — fixing a source document and re-indexing updates the record, never duplicates it
  @edge-case @regression
  Scenario: Re-indexing after editing a source document updates its record rather than duplicating it
    Given a document that has already been re-indexed
    And that document's content has since changed
    When the re-index pipeline runs again
    Then the record for that document should be updated to the new content
    And no duplicate record should exist for that document

  # Why: A run interrupted partway is safely resumable — already-published episodes are durable, a re-run completes the rest
  @edge-case
  Scenario: A run interrupted partway through can be safely re-run to completion
    Given a re-index run that is interrupted after publishing some but not all documents
    When the re-index pipeline is run again over the whole corpus
    Then every document should end up published exactly once in the store
    And no duplicate record should result from the documents published before the interruption

  # Why: The backfill happy path — a reviewed staged payload publishes through the same relay path as deterministic re-index
  @edge-case
  Scenario: A reviewed backfill payload is published on the next run
    Given a backfill payload in the staging area that has been marked as reviewed
    When the re-index pipeline runs
    Then that backfill payload should be published through the relay
    And it should be stored as a typed record like any deterministically parsed payload

  # Why: Stream-vs-store audit (AC) — after a run, every published episode is accounted for as ingested or dead-lettered
  @edge-case
  Scenario: After a run every published episode is accounted for as ingested or dead-lettered
    Given a completed full-corpus re-index run
    When the published episodes are audited against the store
    Then every published episode should be either stored or recorded on the dead-letter subject
    And no published episode should be unaccounted for

  # Why: Idempotency at the publish layer — re-publishing the same parsed document twice yields a single stored record
  @edge-case @regression
  Scenario: Publishing the same parsed document twice yields a single stored record
    Given a document parsed into a typed payload
    When the same payload is published twice through the relay
    Then exactly one record should exist for that document's natural key

  # ──────────────── Edge cases — security / injection ─────────────────

  # Why: Memory content is data, never instructions — hostile prose must round-trip inert through the pipeline
  @edge-case @negative
  Scenario: A document whose body contains injection-shaped text is published verbatim and stays inert
    Given a document whose body contains database commands and prompt-injection text
    When the re-index pipeline parses and publishes the document
    Then the published payload should contain that text byte-for-byte as written
    And no command in the content should be executed during parsing or publishing

  # Why: The corpus walk must stay inside its root — a crafted path must not let the pipeline read outside the corpus
  @edge-case @negative
  Scenario: A path-traversal filename in the corpus cannot make the pipeline read outside the corpus root
    Given a corpus entry whose name contains path-traversal segments
    When the re-index pipeline walks the corpus
    Then only documents within the corpus root should be read
    And no file outside the corpus root should be published

  # Why: The review gate is operator-controlled — a payload cannot mark itself reviewed to bypass the gate
  @edge-case @negative
  Scenario: A backfill payload that claims to be reviewed within its own content is still gated
    Given a staged backfill payload whose own content asserts that it has been reviewed
    And no operator-controlled review marker exists for that payload
    When the re-index pipeline runs
    Then that backfill payload should not be published

  # ──────────────────── Edge cases — concurrency ──────────────────────

  # Why: Two operators (or a retry overlapping the original) must not double the corpus
  @edge-case @regression
  Scenario: Two re-index runs started at the same time converge to a single stored outcome
    Given two re-index runs over the same corpus started at the same time
    When both runs publish their episodes through the relay
    Then exactly one record should exist for each document's natural key
    And no duplicate record should be created by the overlapping runs

  # ─────────────── Edge cases — integration boundaries ────────────────

  # Why: Zero capture loss — a relay or store outage mid-run must surface as failure, never a silent partial run
  @edge-case @negative @regression
  Scenario: A relay or store outage mid-run fails loudly and loses no document
    Given a re-index run in progress when the relay becomes unreachable
    When the in-flight publishes fail
    Then the run should report failure with the affected documents named
    And no document should be silently skipped
    And re-running the pipeline should publish every document that did not reach the store

  # Why: Single write path — staged backfill is handled byte-identically to deterministic re-index, no second code path
  @edge-case
  Scenario: Reviewed backfill payloads publish through the same relay path as deterministically parsed documents
    Given a corpus of recognized documents and a reviewed backfill payload in staging
    When the re-index pipeline runs
    Then both the parsed documents and the reviewed backfill payload should be published through the same relay path
    And both should be stored by the same deterministic writer
Write re-index-pipeline_assumptions.yaml
44 lines
# Assumptions manifest for re-index-pipeline.feature
# Generated by /feature-spec

feature: "Re-index Pipeline"
generated: "2026-06-13T20:05:00Z"
stack: "python"
review_required: false

assumptions:
  - id: "ASSUM-001"
    scenario: "A full guardkit corpus re-index completes within the time budget"
    assumption: "A full guardkit re-index completes in under 5 minutes"
    confidence: high
    basis: "FEAT-MEM-07 acceptance criterion and build-plan throughput gate both state < 5 minutes for the full guardkit corpus"
    human_response: "confirmed"

  - id: "ASSUM-002"
    scenario: "A reviewed backfill payload is published on the next run"
    assumption: "Backfill payloads are staged under backfill/staging/"
    confidence: high
    basis: "FEAT-MEM-07 acceptance criterion: 'Backfill payloads land in backfill/staging/ and publish only after review flag'"
    human_response: "confirmed"

  - id: "ASSUM-003"
    scenario: "An unreviewed backfill payload is not published"
    assumption: "A backfill payload publishes only when an operator-controlled review marker, held outside the payload content, is present"
    confidence: medium
    basis: "AC states 'publish only after review flag'; the exact form of the marker (sidecar file, manifest entry, directory move) is not specified in the build plan"
    human_response: "confirmed"

  - id: "ASSUM-004"
    scenario: "A document matching no known parser is recorded as unrecognized"
    assumption: "An unrecognized document is skipped and recorded in the run report, not published and not aborting the run"
    confidence: medium
    basis: "The 'no silent losses' invariant requires accounting; the build plan does not state skip-vs-park behaviour on the publisher side"
    human_response: "confirmed"

  - id: "ASSUM-005"
    scenario: "Published episodes are structured so the relay routes them to the deterministic writer"
    assumption: "Structured episodes are published with content_format 'json' and an explicit payload_type so the relay routes them to the deterministic writer"
    confidence: high
    basis: "src/fleet_memory/relay/schema.py (MemoryEpisodeV1) and src/fleet_memory/relay/service.py route json + payload_type episodes to the deterministic writer"
    human_response: "confirmed"
Write re-index-pipeline_summary.md
75 lines
# Feature Spec Summary: Re-index Pipeline

**Stack**: python
**Generated**: 2026-06-13T20:05:00Z
**Scenarios**: 30 total (5 smoke, 6 regression)
**Assumptions**: 5 total (3 high / 2 medium / 0 low confidence)
**Review required**: No

## Scope

The re-index pipeline (FEAT-MEM-07, part a) walks guardkit's authoritative
markdown corpus — seed modules, ADRs, review reports, and completed-task
outcomes — and turns each document into a typed payload (`seed_module`, `adr`,
`review_report`, `build_outcome`) via deterministic, front-matter/house-format
parsers with no language-model call. Each payload is published as a
`MemoryEpisodeV1` (content_format `json` + explicit `payload_type`) through the
live relay, which dispatches it to the FEAT-MEM-03 deterministic writer. Full-
corpus runs are idempotent and re-runnable: idempotency, versioned upsert, and
natural-key dedup are enforced downstream by the writer's content-hash upsert,
so a second run over an unchanged corpus is a no-op and an edited source updates
its record rather than duplicating it. Part (b) adds a backfill staging area
(`backfill/staging/`) for Fable-authored payloads that publish only after an
operator-controlled human review marker — gating frontier-authored content
behind review while reusing the same single write path (DECISION-DF-001: Fable
for offline authoring only, zero cloud on the publish path).

## Scenario Counts by Category

| Category | Count |
|----------|-------|
| Key examples (@key-example) | 8 |
| Boundary conditions (@boundary) | 5 |
| Negative cases (@negative) | 10 |
| Edge cases (@edge-case) | 12 |

(Tags overlap: several scenarios carry both `@edge-case` and `@negative`, or
`@boundary` and `@negative`; the column counts every tag occurrence.
`@smoke`: 5, `@regression`: 6.)

## Deferred Items

None. All four proposal groups and the 6-scenario security/concurrency/
integration expansion were accepted.

## Open Assumptions (low confidence)

None. All 5 assumptions resolved at medium or high confidence and confirmed —
no `REVIEW REQUIRED` flag. Two medium-confidence items worth a glance during
planning:

- **ASSUM-003** — review-gate mechanism: an operator-controlled marker held
  *outside* the payload content. The concrete form (sidecar file, manifest
  entry, directory move) is a design decision for `/feature-plan`.
- **ASSUM-004** — unrecognized documents are skipped and recorded in the run
  report (accounted for, run not aborted), rather than parked/dead-lettered.

## Related acceptance criteria not specced here

Two FEAT-MEM-07 acceptance criteria sit adjacent to this pipeline and are
touched only lightly (one audit edge-case scenario each); they may warrant
their own scope in `/feature-plan`:

- Stream-vs-store audit script reporting 100% accounted (ingested or DLQ'd).
- Probe-set parity report generated against the re-indexed corpus.

## Integration with /feature-plan

This summary can be passed to `/feature-plan` as a context file:

    /feature-plan "Re-index Pipeline" \
      --context features/re-index-pipeline/re-index-pipeline_summary.md

Note: `@task:<TASK-ID>` tags are intentionally absent — `/feature-plan`
Step 11 links scenarios to the tasks it creates.
Now the mandatory normalization/parser-validation backstop:

Bash Normalize and validate the feature file
IN
(source .venv/bin/activate 2>/dev/null; python -m installer.core.commands.lib.feature_spec_normalize features/re-index-pipeline/re-index-pipeline.feature; echo "EXIT=$?")

OUT
/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.venv/bin/python: Error while finding module specification for 'installer.core.commands.lib.feature_spec_normalize' (ModuleNotFoundError: No module named 'installer')
EXIT=1
The normalizer module isn't shipped in this repo. Let me check and fall back to validating with the official gherkin parser directly.

Bash Locate normalizer and check gherkin parser
IN
cd /Users/richardwoollcott/Projects/appmilla_github/fleet-memory; find . -name "feature_spec_normalize*" -not -path "*/.git/*" 2>/dev/null | head; echo "---gherkin available?---"; (source .venv/bin/activate 2>/dev/null; python -c "import gherkin; print('gherkin ok', gherkin.__file__)" 2>&1 | head -3)

OUT
---gherkin available?---
gherkin ok /Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.venv/lib/python3.14/site-packages/gherkin/__init__.py
Bash Validate feature with official gherkin parser
IN
cd /Users/richardwoollcott/Projects/appmilla_github/fleet-memory; source .venv/bin/activate 2>/dev/null; python -c "
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner
import sys
p = Parser()
with open('features/re-index-pipeline/re-index-pipeline.feature') as f:
    src = f.read()
try:
    doc = p.parse(TokenScanner(src))
    feat = doc['feature']
    scen = [c for c in feat['children'] if 'scenario' in c]
    print('PARSE OK — scenarios/outlines:', len(scen))
    sys.exit(0)
except Exception as e:
    print('PARSE FAILED:', e); sys.exit(1)
"; echo "EXIT=$?"

OUT
PARSE OK — scenarios/outlines: 30
EXIT=0
The official gherkin parser (the same one /feature-plan Step 11 uses downstream) parses all 30 scenarios cleanly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE SPEC COMPLETE: Re-index Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files written:

re-index-pipeline.feature
re-index-pipeline_assumptions.yaml
re-index-pipeline_summary.md
Scenarios: 30 total

@key-example: 8    @boundary: 5
@negative: 10    @edge-case: 12
@smoke: 5      @regression: 6
Assumptions: 5 total

high: 3 (auto-proceed) — 5-min budget, backfill/staging/ location, json+payload_type routing
medium: 2 (Coach review recommended) — review-gate marker form, unrecognized-doc handling
low: 0
No REVIEW REQUIRED flag. Validated with the official gherkin parser (exit 0).

Note: the documented Step-8 backstop python -m installer.core.commands.lib.feature_spec_normalize isn't shipped in this consumer repo (it lives in the guardkit installer), so I validated directly with the same gherkin parser it wraps. No wrapped step lines were present to collapse.

Deferred: 0 scenario groups.

Two FEAT-MEM-07 acceptance criteria sit adjacent to this pipeline and are only lightly touched (one audit scenario): the stream-vs-store audit script and the probe-set parity report. Worth deciding in planning whether they belong in this feature or their own.

Next steps:

Review: re-index-pipeline.feature
Pass to feature-plan: /feature-plan "Re-index Pipeline" --context features/re-index-pipeline/re-index-pipeline_summary.md

