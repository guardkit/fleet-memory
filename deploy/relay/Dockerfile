# fleet-memory relay image — durable MEMORY-stream consumer -> Postgres+pgvector.
#
# Build context is the REPO ROOT (see deploy/relay/docker-compose.yml build.context),
# so the src/ tree and pyproject.toml are available to the install.
FROM python:3.12-slim

WORKDIR /app

# Install the package (src layout: [tool.setuptools.packages.find] where=["src"]).
# faststream[cli] (needed by `faststream run`) is pulled in via the pinned dependency.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run the relay app. Settings are supplied via FLEET_MEMORY_* env vars (env_file).
CMD ["faststream", "run", "fleet_memory.app:app"]
