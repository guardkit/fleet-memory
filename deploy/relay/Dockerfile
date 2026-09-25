# fleet-memory relay image — durable MEMORY-stream consumer -> Postgres+pgvector.
#
# Build context is the REPO ROOT (see deploy/relay/docker-compose.yml build.context),
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
# `docker compose -f deploy/relay/docker-compose.yml build` still works.
FROM python:3.14-slim-bookworm@sha256:2e256d0381371566ed96980584957ed31297f437569b79b0e5f7e17f2720e53a

WORKDIR /app

# Install the package (src layout: [tool.setuptools.packages.find] where=["src"]).
# faststream[cli] (needed by `faststream run`) is pulled in explicitly via the relay extra.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[relay]"

# Run the relay app. Settings are supplied via FLEET_MEMORY_* env vars (env_file).
CMD ["faststream", "run", "fleet_memory.app:app"]
