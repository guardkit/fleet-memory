# fleet-memory resident MCP service image — HTTP MCP over the NAS Postgres store.
#
# Build context is the REPO ROOT (see deploy/mcp/docker-compose.yml build.context),
# so the src/ tree and pyproject.toml are available to the install.
#
# THE BASE IS PINNED BY DIGEST, and it is the factory's one base image
# (25 September 2026). This image is now built as part of a Forge release
# (forge/release/manifest.yaml names it), and a release build refuses any
# Dockerfile that pins no digest, and refuses a digest that is not the
# release's single base: a release has one base image, or it has two supply
# chains under one name. `python:3.12-slim` was also not a pin at all — two
# machines building it a week apart get different bytes, which is the whole
# thing the release path exists to end.
#
# Nothing else here changes, and a plain
# `docker compose -f deploy/mcp/docker-compose.yml build` still works.
FROM python:3.14-slim-bookworm@sha256:2e256d0381371566ed96980584957ed31297f437569b79b0e5f7e17f2720e53a

WORKDIR /app

# Install the package (src layout: [tool.setuptools.packages.find] where=["src"]).
COPY pyproject.toml ./
COPY uv.lock ./
COPY src ./src

# THE VERSIONS ARE THIS REPOSITORY'S OWN LOCKED ONES, not whatever the index
# serves on the day of the build (18 October 2026, security fix list A6).
#
# pyproject.toml declares RANGES, and a developer's environment is built from
# uv.lock. Installing the ranges straight from the index makes every build a
# different program, and lets a broken or compromised release on the index into
# the image even after uv.lock has been fixed. So the lock is turned into a pip
# constraints file and the install is held to it, the same way Jarvis's image
# does it. The one package the lock resolves from a local path (this package
# itself) is left out: a constraint is a version, and it has no version on an
# index.
#
# This is NOT a second source of truth. uv.lock stays the one place the
# versions are written; this step only reads it.
RUN python - <<'PY'
import tomllib
locked = tomllib.load(open("uv.lock", "rb"))
with open("/tmp/constraints.txt", "w") as out:
    for package in locked["package"]:
        source = package.get("source", {})
        if "registry" not in source:
            continue
        out.write(f"{package['name']}=={package['version']}\n")
PY

RUN pip install --no-cache-dir -c /tmp/constraints.txt .

# RUN AS AN ORDINARY USER, NOT ROOT (16 October 2026). The same fixed number,
# 1000:1000, as the relay image and the factory's other images. The service writes
# nothing of its own: it serves HTTP on ports above 1024 and tiktoken's download
# cache goes under /tmp, which every user can write. The home folder exists so a
# library that looks for one finds a writable place.
RUN groupadd --system --gid 1000 memory \
    && useradd --system --uid 1000 --gid 1000 --home-dir /home/memory --create-home \
       --shell /usr/sbin/nologin memory

USER memory

# Run the MCP server. Settings are supplied via FLEET_MEMORY_* env vars;
# FLEET_MEMORY_MCP_TRANSPORT=http makes it a resident HTTP service.
CMD ["python", "-m", "fleet_memory.mcp"]
