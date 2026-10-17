"""One narrow memory door per build sandbox (17 October 2026).

Each build sandbox gets its own port on the memory service, and that port
serves only the projects listed for it. FLEET_MEMORY_MCP_SANDBOX_DOORS names
the doors as comma-separated ``<port>:<project>|<project>`` entries, for
example ``8006:proj_a|proj_b,8007:proj_c``. A door keeps every rule of the
single narrow door (FLEET_MEMORY_MCP_SANDBOX_PORT) and adds one: a search,
write or listing for a project outside its own list is refused.

A malformed value stops the service at start, so a typing mistake can never
leave a door open to every project. A project may belong to one door only,
because two sandboxes sharing a project would share its memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Searches accept only these names (fleet_memory.retrieval.search_request), so a
# door listing anything else could never serve it; refusing it at start makes the
# mistake visible.
_PROJECT_NAME = re.compile(r"[a-z0-9_]+")
_PORT = re.compile(r"[0-9]{1,5}")

# THE SANDBOX'S NARROW DOOR (15 October 2026). Code in a build can reach the
# sandbox's door, so a write there must not plant records where the factory or
# its agents will read them as their own. These are the factory's and its
# agents' shelves (memory projects); the narrow door never writes on them,
# and no door may serve them (17 October 2026): the guardkit shelf, for one,
# holds build outcomes from many projects, so reading it would leak them. The
# match is exact after lower-casing, as searches are exact. The list is in code
# so that adding a product changes nothing; a new agent shelf needs a release.
RESERVED_PROJECTS = (
    "guardkit",
    "guardkitfactory",
    "forge",
    "fleet_memory",
    "nats_core",
    "specialist_agent",
    "jarvis",
    "office_manager",
    "ai_transition",
    "software_factory",
)

# The same words for every refusal, naming no project: neither the one asked
# for nor the door's own.
DOOR_PROJECT_REFUSAL = "this sandbox's memory door does not serve that project"


@dataclass(frozen=True)
class SandboxDoor:
    """One door: the port it listens on and the only projects it serves."""

    port: int
    projects: frozenset[str]


def parse_sandbox_doors(value: str, *, main_port: int) -> list[SandboxDoor]:
    """Read FLEET_MEMORY_MCP_SANDBOX_DOORS; raise ValueError if it is malformed.

    An empty value means no per-project doors. Ports must be whole numbers
    from 1 to 65535, differ from each other and from the main server's port;
    each door needs at least one project; a project may appear once only.
    """
    doors: list[SandboxDoor] = []
    if not value.strip():
        return doors
    seen_ports: set[int] = set()
    seen_projects: set[str] = set()
    for entry in value.split(","):
        entry = entry.strip()
        port_text, sep, projects_text = entry.partition(":")
        if not entry or not sep:
            raise ValueError(
                "FLEET_MEMORY_MCP_SANDBOX_DOORS: each entry must be "
                f"'<port>:<project>|<project>', not {entry!r}"
            )
        port_text = port_text.strip()
        if not _PORT.fullmatch(port_text) or not 1 <= int(port_text) <= 65535:
            raise ValueError(f"FLEET_MEMORY_MCP_SANDBOX_DOORS: {port_text!r} is not a port number")
        port = int(port_text)
        if port == main_port:
            raise ValueError(
                f"FLEET_MEMORY_MCP_SANDBOX_DOORS: port {port} is the main server's own port"
            )
        if port in seen_ports:
            raise ValueError(f"FLEET_MEMORY_MCP_SANDBOX_DOORS: port {port} is listed twice")
        seen_ports.add(port)
        projects = [name.strip() for name in projects_text.split("|")]
        if not projects or any(not name for name in projects):
            raise ValueError(
                f"FLEET_MEMORY_MCP_SANDBOX_DOORS: the door on port {port} has an empty "
                "project name; list at least one project, separated by '|'"
            )
        for name in projects:
            if not _PROJECT_NAME.fullmatch(name):
                raise ValueError(
                    f"FLEET_MEMORY_MCP_SANDBOX_DOORS: {name!r} is not a project name "
                    "(lower-case letters, digits and '_' only)"
                )
            if name.lower() in RESERVED_PROJECTS:
                raise ValueError(
                    f"FLEET_MEMORY_MCP_SANDBOX_DOORS: {name!r} is a factory shelf and "
                    "cannot be on a sandbox door"
                )
            if name in seen_projects:
                raise ValueError(
                    f"FLEET_MEMORY_MCP_SANDBOX_DOORS: project {name!r} is listed more than "
                    "once; a project belongs to one door and one sandbox only"
                )
            seen_projects.add(name)
        doors.append(SandboxDoor(port=port, projects=frozenset(projects)))
    return doors


def check_door_project(project: object, allowed_projects: frozenset[str] | None) -> None:
    """Raise ValueError unless this door serves ``project``.

    ``allowed_projects`` None is the single narrow door, or the main server,
    which serve every project as before. A missing or empty project is refused
    on a door with a list, never read as "every project".
    """
    if allowed_projects is None:
        return
    if not isinstance(project, str) or project not in allowed_projects:
        raise ValueError(DOOR_PROJECT_REFUSAL)
