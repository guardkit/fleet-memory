# fleet-memory resident MCP service image — HTTP MCP over the NAS Postgres store.
#
# Build context is the REPO ROOT (see deploy/mcp/docker-compose.yml build.context),
# so the src/ tree and pyproject.toml are available to the install.
FROM python:3.12-slim

WORKDIR /app

# Install the package (src layout: [tool.setuptools.packages.find] where=["src"]).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run the MCP server. Settings are supplied via FLEET_MEMORY_* env vars;
# FLEET_MEMORY_MCP_TRANSPORT=http makes it a resident HTTP service.
CMD ["python", "-m", "fleet_memory.mcp"]
