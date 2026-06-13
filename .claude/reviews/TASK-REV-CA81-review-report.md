# Review Report: TASK-REV-CA81 — Plan: Memory Storage Substrate (FEAT-MEM-01)

## Review Details
- **Mode**: Decision Analysis
- **Depth**: Standard
- **Date**: 2026-06-12
- **Reviewer**: software-architect agent
- **Context A**: focus=all, trade-off=hermetic correctness, assumptions=defaults+verify (ASSUM-004/006/008)
- **Graphiti context**: none available (new project knowledge graph)
- **Context sources**: storage-substrate_summary.md, storage-substrate.feature (34 scenarios), storage-substrate_assumptions.yaml, phase-core-build-plan.md, RUNBOOK-nas-postgres-deploy.md

---

## Executive Summary

FEAT-MEM-01 lands a complete storage substrate from a repo that currently contains zero Python. The non-negotiable constraint — the full test suite passes with the NAS powered off — drives every architectural decision. The three decision axes that have genuine alternatives are ephemeral Postgres provisioning, the embed callable design, and the app-shell form. The remaining two axes (settings/profiles, pgvector enablement) have one clearly correct answer each given the constraints. Thirteen tasks are identified across five implementation waves, with a clear operator-handoff boundary separating the automatable NAS file-authoring from the live NAS deployment. Three low-confidence assumption values (ASSUM-004/006/008) are explicitly assigned to verification tasks with record-and-revise acceptance criteria.

---

## Technical Options Analysis

### Axis 1 — Ephemeral test Postgres provisioning

**Option A: Docker Compose file in `deploy/local/` with random host port via env + pytest session fixture**

The build plan explicitly names `deploy/local/` as a compose file. A `docker compose -p fleet_memory_test_${UNIQUE_ID} up -d` call inside a session-scoped pytest fixture, where `UNIQUE_ID` is derived from `uuid.uuid4().hex[:8]`, gives a distinct compose project name per worker, a random host port (port: `"${PGPORT:-0}"` in the compose file resolves to an OS-assigned port, or the fixture sets an explicit random port in the 49152–65535 range before invoking compose), and a `--rm` + `docker compose -p ... down -v` in a `finally` block guarantees cleanup even on SIGINT via `atexit`. The compose file itself is the operator-readable artifact; `deploy/local/` mirrors `deploy/nas/` in directory structure, which maintains one NAS-container convention. Parallel worktree isolation requires the fixture to mint a fresh project name on every invocation; `pytest-xdist`-style worker ID is available as `PYTEST_XDIST_WORKER` if xdist is used, or `PYTEST_CURRENT_TEST` can seed the name otherwise.

Pros: build-plan mandated artifact, operator-readable, mirrors NAS directory, compose project name isolation is robust, cleanup on abort via `atexit` + `docker compose down`, no extra dependency.
Cons: relies on Docker CLI being in PATH; fixture must parse `docker port` output to retrieve the dynamically assigned host port.

**Option B: testcontainers-python with `PostgresContainer`**

`testcontainers` handles port assignment, container lifecycle, health-waiting, and cleanup (via `__exit__` and `ResourceReaper` RYUK sidecar). Parallel safety is inherent — each instantiation gets its own container. RYUK cleans orphans even on SIGKILL.

Pros: RYUK sidecar handles aborted-run cleanup including SIGKILL, no compose file authoring needed for the test tier.
Cons: RYUK sidecar is an extra container and an extra network dependency; `testcontainers` adds a transitive dependency; the build plan explicitly says compose file in `deploy/local/` which is the operator reference artifact (having two approaches diverges the directory structure); pgvector image (`pgvector/pgvector:pg16`) is not the default postgres image so image must be overridden; no operator-readable compose parallel to the NAS compose. Hermetic correctness is satisfied but at the cost of diverging from the stated topology.

**Option C: Raw `docker run` in a pytest fixture**

`subprocess.run(["docker", "run", "-d", "--rm", "-p", "0:5432", "pgvector/pgvector:pg16", ...])` inside a session fixture, capturing the container ID and port.

Pros: no compose, no extra deps, maximum transparency.
Cons: no compose file means no operator reference, no `docker compose down` cleanup shorthand, no ability to add init SQL side-cars easily; `--rm` only fires on normal container stop, not on Docker daemon restart or SIGKILL; more fragile than either alternative.

**★ Recommendation: Option A** — Docker Compose in `deploy/local/` with a session-scoped pytest fixture. The build plan mandates this artifact explicitly. Project-name isolation (`-p fleet_memory_test_${uid}`) satisfies parallel-worktree isolation without any additional tooling. An `atexit.register` call in the fixture wrapping `subprocess.run(["docker", "compose", "-p", project, "down", "-v"])` covers aborted runs; the pytest `request.addfinalizer` covers normal teardown. The BDD scenarios "Parallel test runs each get their own isolated ephemeral instance", "An aborted test run still leaves no trace behind", and "An explicitly requested integration run fails clearly when no ephemeral instance can start" are all satisfied. When Docker is absent, the fixture raises `pytest.skip` with a diagnostic message — satisfying the last negative scenario without a hang.

---

### Axis 2 — Embed function design

**Option A: Plain async httpx callable (build plan mandates httpx)**

A module-level `async def embed(texts: list[str]) -> list[list[float]]` that uses `httpx.AsyncClient` with a `timeout=settings.embed_timeout_s` (default 10.0). Dimension validation is a post-call assertion inside the function body: if `len(vector) != 768` raise `EmbedDimensionError`. The function is injectable — tests replace it with a `fake_embed` fixture that returns deterministic unit vectors. For `AsyncPostgresStore`, the `index` config `embed` field accepts any callable with this signature.

Pros: exactly what the build plan specifies, minimal deps, timeout is a first-class parameter, fake replacement is trivial (a pure function), no framework lock-in.
Cons: manual OpenAI-compatible payload shaping; re-implements the request/response cycle rather than delegating.

**Option B: openai-python client (`AsyncOpenAI` with `base_url`)**

The OpenAI Python client with `base_url="http://.../v1"` and `api_key="unused"` talks to llama-swap's OpenAI-compatible endpoint.

Pros: well-tested HTTP layer, retry built-in.
Cons: `openai` package is a heavyweight dep (httpx is already in the FastStream dep tree, openai is not); its retry logic may obscure the 10 s timeout intent; for a `base_url` override it is cargo-culting the client for a simpler pattern; replacing it with a fake is heavier (mock client object vs plain callable).

**Option C: LangChain embeddings class**

`LangChainEmbeddings` wrapping `nomic`.

Pros: familiar to LangGraph users.
Cons: LangChain is a heavy transitive dep, introduces a second abstraction layer over what `AsyncPostgresStore.index.embed` already is, couples the store tier to the LangChain ecosystem unnecessarily. Clearly wrong for this stack.

**★ Recommendation: Option A** — plain async httpx callable with injectable fake. Dimension validation belongs in the callable body so it fires before any write attempt reaches the store, satisfying the "loud failure on mismatch, never truncate silently" requirement. The fake for unit tests is a one-line lambda returning `[[0.1] * 768] * len(texts)`. ASSUM-008 (embed timeout 10 s) is encoded as `settings.embed_timeout_s: float = 10.0` and verified against the actual httpx connection + read timeout semantics in the integration test task.

---

### Axis 3 — App shell / lifespan integration

**Option A: Minimal FastStream app shell now (template idiom, lifespan wires pool+store, no subscribers)**

A `src/fleet_memory/app.py` containing a `FastStream(broker)` app with a `lifespan` context manager that creates the `AsyncPostgresStore`, calls `store.setup()`, and stores the instance on the app state. No `@broker.subscriber` decorators are wired yet. FEAT-MEM-04 adds the first subscriber into the already-wired shell.

Pros: respects the declared `nats-asyncio-service` template idiom and CLAUDE.md architectural constraints; FEAT-MEM-02/03/04 each build into an already-wired shell rather than having to introduce the FastStream layer; lifespan testing pattern (`TestNatsBroker`) is available from day one; the broker singleton (required by the template pattern) is declared early.
Cons: introduces a NATS broker dependency at FEAT-MEM-01 time even though FEAT-MEM-01 itself has no subscribers; the broker needs a NATS URL in settings even before FEAT-MEM-04.

**Option B: Plain asyncio entrypoint with `contextlib.AsyncExitStack`**

A `src/fleet_memory/store_lifecycle.py` module exposing `async_context_manager` that enters `AsyncPostgresStore` and returns it; a thin `main.py` that uses `AsyncExitStack` to combine pool + store lifecycles.

Pros: zero NATS dependency at FEAT-MEM-01 time; cleaner separation of the storage lifecycle from the messaging layer; testable in isolation without a TestNatsBroker.
Cons: means FEAT-MEM-04 must retroactively introduce FastStream and restructure the entrypoint; creates a fork in the template idiom that must later be unified; the lifespan context manager pattern works fine in both options but the FastStream shape is what the template and subsequent features expect.

**Option C: Defer app shell, expose only store factory + async context manager**

No app shell at FEAT-MEM-01; just `store_factory.py` with `async_store_context(settings)` as the sole public interface.

Pros: minimal surface, maximally deferrable.
Cons: same retroactive-introduction cost as Option B but worse — defers even the context manager shape; FEAT-MEM-02/03 builds on nothing; the gap from no-shell to full-shell grows linearly with each deferred feature.

**★ Recommendation: Option A** — minimal FastStream app shell with lifespan-wired store and no subscribers. The CLAUDE.md constraint ("Handler → Service unidirectional; lifespan-managed pool") is written against the FastStream idiom specifically. The broker is declared at module level but configured from settings; a NAS-off NATS_URL is not needed for FEAT-MEM-01's tests because `TestNatsBroker` patches the connection. A `FLEET_MEMORY_NATS_URL` setting field with a reasonable default keeps the settings surface forward-compatible at zero cost. FEAT-MEM-04 slots subscribers into the shell without restructuring.

---

### Axis 4 — Settings / profiles

One correct answer: a single `pydantic-settings` `BaseSettings` subclass with `env_prefix = "FLEET_MEMORY_"` and `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`. Fields: `pg_dsn: PostgresDsn`, `embed_url: AnyHttpUrl`, `embed_model: str = "nomic-embed-text-v1.5"`, `embed_dims: int = 768`, `embed_timeout_s: float = 10.0`, `pg_pool_min: int = 2`, `pg_pool_max: int = 10`, `pg_connect_timeout_s: float = 10.0`, `nats_url: str = "nats://localhost:4222"`. The `.env.example` file documents three blocks: `mac-dev` (NAS DSN, GB10 embed URL), `test` (ephemeral DSN, GB10 embed URL — integration tier uses real nomic per ASSUM-012), and comments pointing to FEAT-MEM-04 for the `gb10-runtime` profile (OD-5). The three placeholder values for ASSUM-004/006/008 appear as the `pg_pool_max`, `pg_connect_timeout_s`, and `embed_timeout_s` defaults respectively; each has a comment noting its placeholder status and directing the implementer to the verification task.

---

### Axis 5 — pgvector enablement

**Option A: `docker-entrypoint-initdb.d` init SQL in the compose file (both local and NAS)**

Both compose files mount a `./initdb/01_extensions.sql` file into `/docker-entrypoint-initdb.d/`. The SQL is `CREATE EXTENSION IF NOT EXISTS vector;`. This runs exactly once on first container start, before any application connection.

Pros: zero application code; idempotent (`IF NOT EXISTS`); runs before any `store.setup()` call; visible in the repo alongside the compose file; no migration tooling needed for a one-liner.

**Option B: migrations/ SQL applied by a script**

A `migrations/001_enable_pgvector.sql` applied by a `scripts/migrate.sh` that runs `psql` against the target DSN.

Pros: migrations/ dir exists and is empty; extension enablement is one migration among others.
Cons: `migrations/` dir exists but the build plan does not describe a migration runner (no alembic, no flyway); a hand-rolled migration script adds tooling surface; `store.setup()` already creates the store schema, so migrations/ would own only the extension; asymmetric tooling (two mechanisms: store.setup() + hand-rolled migrations) is worse than one.

**Option C: `store.setup()`-adjacent code**

`await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")` before calling `store.setup()`.

Pros: single Python entrypoint.
Cons: requires a superuser connection (or at least the `rds_superuser`-equivalent); in the NAS deployment the application user may not have extension-create rights; defeats the "least privilege application user" security principle; the init-db script runs as the `postgres` superuser implicitly.

**★ Recommendation: Option A** — `docker-entrypoint-initdb.d` init SQL in both compose files. Both compose files share the same `initdb/01_extensions.sql` by relative path (`./initdb/` directory within `deploy/local/` and `deploy/nas/` respectively, or a shared `deploy/shared/initdb/` symlinked). This is the correct Postgres idiom: superuser-only DDL at database creation time, application user operates with table-level grants only. The NAS runbook Gate G3 already validates `CREATE EXTENSION IF NOT EXISTS vector` manually; this bakes that gate into the container so it is guaranteed at every fresh deployment.

---

## Recommended Approach

Provision the repo with a single scaffolding task that establishes `pyproject.toml`, `src/fleet_memory/`, `tests/unit/` + `tests/integration/`, `pytest.ini` with `integration` marker excluded by default, and ruff configuration; all identifiers use underscores. The test tier hermeticity architecture uses a Docker Compose file at `deploy/local/docker-compose.yml` with a session-scoped pytest fixture that mints a UUID-seeded compose project name and a random host port, registers `atexit` cleanup for abort safety, and skips with a clear diagnostic when Docker is absent. The embed callable is a plain async httpx function with injectable fake for unit tests and 768-dimension post-call validation. The app shell is a minimal FastStream app with lifespan-wired `AsyncPostgresStore` and no subscribers, forward-compatible with FEAT-MEM-04. Settings use `FLEET_MEMORY_` prefix with the three placeholder assumption values as documented defaults awaiting verification. pgvector is enabled via `initdb/01_extensions.sql` in both compose files. NAS deployment files (`deploy/nas/docker-compose.yml`, `.env.deploy.example`, `deploy.sh`, `smoke.sh`) are authored by an automatable task; the actual NAS deployment execution is a separate operator-handoff task. Specific bullet decisions:

- Ephemeral Postgres: Docker Compose `deploy/local/` + session-scoped pytest fixture with UUID project names and `atexit` cleanup
- Embed callable: plain async httpx, injectable fake, 768-dim post-call guard, `embed_timeout_s` from settings
- App shell: minimal FastStream shell + lifespan, no subscribers, NATS URL in settings for FEAT-MEM-04 forward-compat
- Settings: `FLEET_MEMORY_` prefix, `pg_pool_max=10`, `pg_connect_timeout_s=10.0`, `embed_timeout_s=10.0` as verifiable defaults
- pgvector: `initdb/01_extensions.sql` in both compose files
- Unit tests: fake embed, mock httpx transport, no database, no network — cover settings validation, namespace validation, dimension mismatch, embed timeout, credential hygiene
- Integration tests: `@pytest.mark.integration` gated, ephemeral Postgres + real nomic over Tailscale

---

## Implementation Breakdown

### Task 01 — `scaffold_project_layout`

**task_type:** scaffolding
**complexity:** 3
**dependencies:** none
**estimated_minutes:** 40
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/pyproject.toml`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/src/fleet_memory/__init__.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/__init__.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/__init__.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/__init__.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/pytest.ini`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/ruff.toml`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.gitignore` (update — already exists and modified per git status)

**Acceptance criteria:**
1. `file_exists: pyproject.toml` — contains `[project]` with `name = "fleet_memory"`, `[tool.ruff]` section, and pinned deps for `faststream[nats]`, `pydantic>=2`, `pydantic-settings>=2`, `langgraph-checkpoint-postgres`, `httpx`, `asyncpg`, `pytest`, `pytest-asyncio`, `pytest-anyio`
2. `command_runs: python -m pytest tests/ --collect-only -q` — exits 0 with "no tests ran" (empty test tree is valid)
3. `command_runs: python -m pytest tests/ -q` — exits 0 (no `integration` marker tests collected by default; `addopts = -m "not integration"` confirmed in pytest.ini)
4. `file_exists: src/fleet_memory/__init__.py` — importable: `python -c "import fleet_memory"` exits 0
5. `command_runs: ruff check src/ tests/` — exits 0 against empty package
6. No file in `src/fleet_memory/` or `tests/` contains a hyphen in any Python identifier or filename

**BDD scenarios covered:** "Unit tests pass with no database and no embedding service available" (structural prerequisite — marker exclusion), "An explicitly requested integration run fails clearly when no ephemeral instance can start" (marker gating established here)

---

### Task 02 — `settings_class`

**task_type:** feature
**complexity:** 3
**dependencies:** `scaffold_project_layout`
**estimated_minutes:** 35
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/src/fleet_memory/settings.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/.env.example`

**Acceptance criteria:**
1. `command_runs: python -c "from fleet_memory.settings import Settings; s = Settings(FLEET_MEMORY_PG_DSN='postgresql://u:p@localhost/db', FLEET_MEMORY_EMBED_URL='http://localhost:9000'); assert s.pg_pool_max == 10; assert s.embed_timeout_s == 10.0; assert s.pg_connect_timeout_s == 10.0"` — exits 0 (verifies ASSUM-004/006/008 defaults; values may be revised once asyncpg/httpx actuals are confirmed)
2. `command_runs: python -c "from fleet_memory.settings import Settings; Settings()"` — raises `ValidationError` (no env set, `pg_dsn` and `embed_url` are required — satisfies "Missing required settings prevent startup with a clear message")
3. `file_exists: .env.example` — contains blocks clearly labelled `mac-dev` and `test`, documents all `FLEET_MEMORY_` prefixed fields, and has inline comments on `pg_pool_max`, `pg_connect_timeout_s`, `embed_timeout_s` noting placeholder status and directing to verification
4. `command_runs: python -m pytest tests/unit/test_settings.py -v` — all settings unit tests pass; tests cover: required-field error message names each missing field, all default values match the documented placeholders, `FLEET_MEMORY_` prefix isolation (a `PG_DSN` env without prefix is ignored)
5. No `FLEET_MEMORY_PG_DSN` or `FLEET_MEMORY_EMBED_URL` field accepts an empty string without raising `ValidationError`
6. The settings module imports no NATS broker, no httpx client, no asyncpg — pure pydantic-settings

**BDD scenarios covered:** "Configuration profiles select the correct deployment target from the environment", "Missing required settings prevent startup with a clear message"

---

### Task 03 — `embed_callable`

**task_type:** feature
**complexity:** 4
**dependencies:** `settings_class`
**estimated_minutes:** 45
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/src/fleet_memory/embed.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/src/fleet_memory/errors.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_embed.py`

**Acceptance criteria:**
1. `command_runs: python -m pytest tests/unit/test_embed.py -v` — all tests pass with zero network calls (httpx `MockTransport` used throughout; verified by asserting no real socket is opened)
2. `test_passes: test_embed.py::test_dimension_mismatch_512` — stores attempt with 512-dim vector raises `EmbedDimensionError` naming the actual and expected dimensions
3. `test_passes: test_embed.py::test_dimension_mismatch_769` — same for 769 dims; covers the BDD `@boundary @negative` outline rows
4. `test_passes: test_embed.py::test_embed_timeout` — `MockTransport` that never responds triggers `EmbedTimeoutError` within `embed_timeout_s` seconds (ASSUM-008 verification: confirm that httpx's read timeout mechanism fires at the configured value; record actual observed behavior in a comment in `test_embed.py`)
5. `file_exists: src/fleet_memory/embed.py` — exports `async def embed(texts, settings) -> list[list[float]]` and `make_fake_embed(dims=768) -> callable` factory for test injection
6. `file_exists: src/fleet_memory/errors.py` — exports `EmbedDimensionError`, `EmbedTimeoutError`, `EmbedServiceError` with messages that name the embedding service URL but never contain any database credential

**BDD scenarios covered:** "An embedding of exactly 768 dimensions is stored and searchable", "An embedding with the wrong number of dimensions is rejected" (all 4 outline rows), "A hung embedding service cannot stall store operations indefinitely", "Database credentials never appear in logs or error messages" (partial — embed-side)

---

### Task 04 — `local_ephemeral_compose_and_fixtures`

**task_type:** infrastructure
**complexity:** 5
**dependencies:** `scaffold_project_layout`
**estimated_minutes:** 60
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/local/docker-compose.yml`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/local/initdb/01_extensions.sql`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/conftest.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/conftest.py` (fake embed fixture)

**Acceptance criteria:**
1. `file_exists: deploy/local/docker-compose.yml` — uses image `pgvector/pgvector:pg16`, no fixed host port (port mapping `"${PGPORT:-5432}:5432"` or equivalent that allows env override to an OS-assigned random port), mounts `./initdb` to `/docker-entrypoint-initdb.d`
2. `file_exists: deploy/local/initdb/01_extensions.sql` — contains exactly `CREATE EXTENSION IF NOT EXISTS vector;`
3. `command_runs: python -m pytest tests/integration/ -m integration --collect-only` — exits with skip or "no tests" when Docker is not running, with message containing "Docker" or "container runtime" (satisfies "An explicitly requested integration run fails clearly when no ephemeral instance can start")
4. `test_passes: a minimal integration test that calls the fixture` — the session-scoped `ephemeral_pg` fixture returns a DSN string containing a host port that is not 5432 (random port confirmed), and after the session the compose project is gone (`docker compose -p <project> ps` returns empty)
5. Two simultaneous invocations of the fixture (simulated by creating two fixture instances with different `project_uid` values) produce DSNs on different ports — verifying parallel isolation (satisfies "Parallel test runs each get their own isolated ephemeral instance")
6. `tests/conftest.py` exports `fake_embed` pytest fixture that returns `make_fake_embed(768)` callable; the fixture carries a `scope="function"` default; no database or network is opened when this fixture is used alone

**BDD scenarios covered:** "An ephemeral test instance provides a fresh database for a test run", "Parallel test runs each get their own isolated ephemeral instance", "An aborted test run still leaves no trace behind", "An explicitly requested integration run fails clearly when no ephemeral instance can start", "The full test suite passes with the durable shared instance powered off", "Unit tests pass with no database and no embedding service available"

---

### Task 05 — `store_factory_and_namespace_validation`

**task_type:** feature
**complexity:** 5
**dependencies:** `embed_callable`, `settings_class`
**estimated_minutes:** 55
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/src/fleet_memory/store.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_store_validation.py`

**Acceptance criteria:**
1. `file_exists: src/fleet_memory/store.py` — exports `async_store_context(settings, embed_fn)` as an `asynccontextmanager` that yields a configured `AsyncPostgresStore`; `embed_fn` defaults to the httpx callable but is injectable; `index` config is `{"dims": 768, "embed": embed_fn, "fields": ["content"]}`
2. `test_passes: test_store_validation.py::test_hyphenated_namespace_rejected` — `validate_namespace(("fleet_memory", "my-project", "chunk"))` raises `NamespaceValidationError` with message containing "underscores" (ASSUM-007 enforcement at validation time, before any database call)
3. `test_passes: test_store_validation.py::test_valid_namespace_accepted` — `validate_namespace(("fleet_memory", "fleet_memory", "adr"))` returns without raising
4. `command_runs: python -m pytest tests/unit/test_store_validation.py -v` — all tests pass with no database, no network (no asyncpg import is exercised in the unit tier — the store factory is constructed but `__aenter__` is never called in unit tests)
5. `command_runs: grep -r "import asyncpg\|from asyncpg" tests/unit/` — exits 1 (no direct asyncpg in unit test files — hermeticity of unit tier confirmed)
6. The `async_store_context` function signature accepts `settings: Settings` and `embed_fn: callable | None = None`; if `embed_fn` is `None` it constructs the real httpx embed callable from settings

**BDD scenarios covered:** "A namespace containing hyphens is rejected", "Storing a memory and retrieving it by its key" (factory prerequisite), "The connection pool lives and dies with the service" (context manager shape)

---

### Task 06 — `app_shell_lifespan`

**task_type:** feature
**complexity:** 4
**dependencies:** `store_factory_and_namespace_validation`, `embed_callable`
**estimated_minutes:** 45
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/src/fleet_memory/app.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_app_lifespan.py`

**Acceptance criteria:**
1. `file_exists: src/fleet_memory/app.py` — exports a module-level `broker = NatsBroker(settings.nats_url)` and a `FastStream(broker)` app with a `@asynccontextmanager` lifespan that enters `async_store_context`, stores the store on `broker._state` or app context, and yields; no `@broker.subscriber` decorators present
2. `test_passes: test_app_lifespan.py::test_lifespan_stores_store_on_context` — using `TestNatsBroker` context manager, the lifespan enters and exits cleanly with a fake embed and an in-memory store mock; no real NATS or Postgres connection is required
3. `test_passes: test_app_lifespan.py::test_startup_fails_on_bad_dsn` — when `Settings` is constructed with an unreachable DSN and the lifespan is entered with a real store context (not mocked), a `StartupError` or `asyncpg.InvalidCatalogNameError` propagates within `pg_connect_timeout_s` seconds (ASSUM-006 verification: record the actual observed timeout behavior in a comment; value may be revised from the 10 s default)
4. `command_runs: python -m pytest tests/unit/test_app_lifespan.py -v` — all tests pass; elapsed time for the startup-fail test is under 15 s total (guards against indefinite hang; actual asyncpg timeout recorded)
5. `command_runs: grep -r "from nats\|import nats" src/fleet_memory/store.py src/fleet_memory/embed.py src/fleet_memory/settings.py` — exits 1 (store, embed, and settings layers have zero NATS imports — handler/service boundary respected)
6. `command_runs: python -c "from fleet_memory.app import app, broker"` — exits 0 with no import errors

**BDD scenarios covered:** "The connection pool lives and dies with the service", "The service refuses to start when the database is unreachable", "Missing required settings prevent startup with a clear message" (app entry point validates settings at import/construction time)

---

### Task 07 — `nas_deploy_files`

**task_type:** declarative
**complexity:** 4
**dependencies:** `local_ephemeral_compose_and_fixtures` (for consistency of compose patterns and `initdb/` convention)
**estimated_minutes:** 50
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/nas/docker-compose.yml`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/nas/initdb/01_extensions.sql`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/nas/.env.deploy.example`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/nas/deploy.sh`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/deploy/nas/smoke.sh`

**Acceptance criteria:**
1. `file_exists: deploy/nas/docker-compose.yml` — uses `pgvector/pgvector:pg16`, service name `fleet_memory_postgres`, `restart: unless-stopped`, bind mount of `${NAS_DOCKER_ROOT}/pgdata:/var/lib/postgresql/data`, port `5432:5432`, `env_file: .env` (compose auto-loads `POSTGRES_PASSWORD`)
2. `file_exists: deploy/nas/deploy.sh` — is executable (`chmod +x`); contains Gates G2 inline as bash conditional blocks with PASS/FAIL echo labels; sources `.env.deploy`; uses `set -euo pipefail`; performs rsync, remote `.env` render, and `docker compose up -d` exactly as described in runbook Phases 2–3; no `sshpass`, no plain-text passwords in script body
3. `file_exists: deploy/nas/smoke.sh` — is executable; contains Gates G3, G4, G5 inline with PASS/FAIL labels as in the runbook; `$SSH ... pg_isready` for G3, direct `psql` over DSN for G4, `ls pgdata/PG_VERSION` for G5; script exits non-zero on any gate failure
4. `file_exists: deploy/nas/.env.deploy.example` — contains the five fields from the runbook credentials table (`NAS_HOST`, `NAS_USER`, `NAS_SSH_PORT`, `NAS_DOCKER_ROOT`, `FLEET_MEMORY_PG_PASSWORD`) with empty values and `openssl rand` instruction comment; committed; `.env.deploy` itself is gitignored
5. `command_runs: bash -n deploy/nas/deploy.sh` — exits 0 (bash syntax check)
6. `command_runs: bash -n deploy/nas/smoke.sh` — exits 0 (bash syntax check)

**BDD scenarios covered:** "The documented smoke check verifies the shared instance end-to-end" (G3–G5 inline in smoke.sh), "Memories on the durable shared instance survive a restart" (G6 cross-referenced in runbook, `restart: unless-stopped` in compose), "The durable shared instance refuses connections from outside the private network" (firewall config documented in compose comments + .env.deploy.example)

---

### Task 08 — `nas_deploy_operator_handoff`

**task_type:** operator_handoff
**complexity:** 1 (no automation — this is a flag, not a build task)
**dependencies:** `nas_deploy_files`
**estimated_minutes:** 0 (operator time not counted in AutoBuild estimate)
**primary files created/touched:** none (operator runs commands on live infrastructure)

**Acceptance criteria:**
1. Operator has executed Phase 0 (SSH key, sudoers, firewall) on the NAS and Gate G0 passes from the Mac
2. Operator has run `deploy/nas/deploy.sh` and Gate G2 passes (container `Up`)
3. Operator has run `deploy/nas/smoke.sh` and Gates G3, G4, G5 all pass
4. Gate G4 specifically: `psql` over LAN/Tailscale DSN returns `1` (NAS reachable from Mac on the actual network path the service uses)
5. Gate G5 specifically: `pgdata/PG_VERSION` reads `16` (data on backed-up volume confirmed)
6. Gate G6 (NAS reboot persistence): after a DSM reboot, G2 and G4 re-pass without intervention

**BDD scenarios covered:** "Memories on the durable shared instance survive a restart", "The documented smoke check verifies the shared instance end-to-end", "The durable shared instance refuses connections from outside the private network"

---

### Task 09 — `unit_test_suite`

**task_type:** testing
**complexity:** 4
**dependencies:** `embed_callable`, `settings_class`, `store_factory_and_namespace_validation`, `app_shell_lifespan`
**estimated_minutes:** 60
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_settings.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_embed.py` (expanded from Task 03 stub)
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_store_validation.py` (expanded from Task 05 stub)
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_app_lifespan.py` (expanded from Task 06 stub)
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/unit/test_credential_hygiene.py`

**Acceptance criteria:**
1. `command_runs: python -m pytest tests/unit/ -v --timeout=30` — all tests pass; `FLEET_MEMORY_PG_DSN` and `FLEET_MEMORY_EMBED_URL` are not set in the test environment (unit tier is hermetic by construction)
2. `test_passes: test_credential_hygiene.py::test_password_not_in_embed_error` — when the embed callable returns `EmbedServiceError`, the error message does not contain the string from `settings.pg_dsn` or any password component extracted from it
3. `test_passes: test_credential_hygiene.py::test_password_not_in_store_error` — when `async_store_context` raises on bad DSN, the propagated exception message does not contain the password portion of the DSN (ASSUM-007 credential hygiene enforcement)
4. `test_passes: test_settings.py::test_missing_pg_dsn_names_field_in_error` — `ValidationError` message from `Settings()` with no env contains the string `"FLEET_MEMORY_PG_DSN"`
5. `command_runs: python -m pytest tests/unit/ -v --timeout=30 -p no:anyio` — the same tests pass without the asyncio event loop (confirms no test accidentally opens a real connection via import-time side effects)
6. Total wall-clock time for `python -m pytest tests/unit/ -v` is under 10 seconds (network-free, confirms no accidental blocking call)

**BDD scenarios covered:** "Unit tests pass with no database and no embedding service available", "Missing required settings prevent startup with a clear message", "Database credentials never appear in logs or error messages", "A namespace containing hyphens is rejected", "An embedding with the wrong number of dimensions is rejected", "A hung embedding service cannot stall store operations indefinitely"

---

### Task 10 — `integration_test_suite_store_semantics`

**task_type:** testing
**complexity:** 6
**dependencies:** `store_factory_and_namespace_validation`, `embed_callable`, `local_ephemeral_compose_and_fixtures`, `app_shell_lifespan`
**estimated_minutes:** 90
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_store_round_trip.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_store_semantics.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_pool_lifecycle.py`

**Acceptance criteria:**
1. `command_runs: python -m pytest tests/integration/ -m integration -v --timeout=120` — all tests pass against the ephemeral Postgres instance with real nomic embeddings over Tailscale (GB10 llama-swap :9000); NAS is not referenced anywhere in the test DSN
2. `test_passes: test_store_round_trip.py::test_put_get_round_trip` — `aput` followed by `aget` returns content byte-identical to what was stored and includes `created_at` / `updated_at` timestamps
3. `test_passes: test_store_semantics.py::test_upsert_replaces_previous` — two `aput` calls to the same key yield exactly one record; `aget` returns the second version only
4. `test_passes: test_store_semantics.py::test_semantic_search_ranking` — after storing memories about "database connection pooling" and "holiday rota planning", `asearch("how do we manage Postgres connections")` returns the pooling memory first with a relevance score field present (confirms real nomic embed round-trip — ASSUM-012 verifying integration tier uses real vectors)
5. `test_passes: test_pool_lifecycle.py::test_pool_opens_and_closes_cleanly` — the store enters, performs an `aput`, and exits without asyncpg connection leak (verified by checking asyncpg connection count before and after via `pg_stat_activity`); ASSUM-006 recorded: actual observed connect-timeout when the DSN points at a closed port — log the value in the test file comment
6. `test_passes: test_pool_lifecycle.py::test_pool_queuing_under_load` — 15 concurrent `aput` calls succeed when `pg_pool_max=10`; no operation dropped; total time is within a 30 s bound (ASSUM-004 verification: record asyncpg's actual queuing behavior — whether it queues or raises `asyncpg.pool.PoolTimeout` — and update the default or the test comment accordingly)

**BDD scenarios covered:** "Storing a memory and retrieving it by its key", "Storing to an existing key replaces the previous memory", "Deleting a memory removes it from retrieval and search", "Semantic search returns memories ranked by relevance to the query", "The connection pool lives and dies with the service", "Operations beyond pool capacity queue rather than fail", "Concurrent writes to the same key leave one complete winner", "A search during a concurrent write never sees a partial memory", "The full test suite passes with the durable shared instance powered off" (uses ephemeral, no NAS DSN)

---

### Task 11 — `integration_test_suite_boundary_and_edge`

**task_type:** testing
**complexity:** 5
**dependencies:** `integration_test_suite_store_semantics`
**estimated_minutes:** 70
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_search_boundaries.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_embed_failures.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_injection_safety.py`

**Acceptance criteria:**
1. `test_passes: test_search_boundaries.py::test_search_limit_1` — with 15 stored memories, `asearch(query, limit=1)` returns exactly 1 result
2. `test_passes: test_search_boundaries.py::test_search_limit_10` — `asearch(query, limit=10)` returns exactly 10 results, the 10 most relevant
3. `test_passes: test_search_boundaries.py::test_search_limit_15` — `asearch(query, limit=15)` returns exactly 15 results
4. `test_passes: test_search_boundaries.py::test_default_limit_at_most_10` — `asearch(query)` with no limit against 15 memories returns at most 10 (ASSUM-002 verified; if `AsyncPostgresStore` default differs, record actual and update settings default)
5. `test_passes: test_embed_failures.py::test_embed_down_no_partial_write` — when the embed callable raises `EmbedServiceError` (injected via overriding `embed_fn`), `aput` raises and a subsequent `aget` for the same key returns `None` (ASSUM-005: no partial write)
6. `test_passes: test_injection_safety.py::test_hostile_content_round_trips_verbatim` — a memory containing `'; DROP TABLE memories; --` round-trips via `aput`/`aget` byte-identical and subsequent `asearch` returns normal results

**BDD scenarios covered:** "Search returns no more results than the requested limit" (all 3 outline rows), "Search without an explicit limit returns at most the default number of results", "Searching an empty store returns no results without error", "Storing a searchable memory fails cleanly when the embedding service is down", "Hostile memory content is stored verbatim and stays inert", "An embedding with the wrong number of dimensions is rejected" (integration confirmation)

---

### Task 12 — `metadata_filter_and_concurrent_write_integration`

**task_type:** testing
**complexity:** 5
**dependencies:** `integration_test_suite_store_semantics`
**estimated_minutes:** 60
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_metadata_filter.py`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/tests/integration/test_concurrent_writes.py`

**Acceptance criteria:**
1. `test_passes: test_metadata_filter.py::test_search_constrained_by_project_filter` — storing memories from `project_a` and `project_b` that are both semantically related to the query; `asearch` with `filter={"project": "project_a"}` returns only `project_a` memories, still ranked by relevance
2. `test_passes: test_metadata_filter.py::test_delete_removes_from_search` — after `aput` then `adelete`, both `aget` and `asearch` return no result for the deleted key
3. `test_passes: test_concurrent_writes.py::test_concurrent_writes_to_same_key` — `asyncio.gather` with two `aput` calls to the same key with different content; after both complete, `aget` returns exactly one of the two versions in full (no blend, no partial — ASSUM-003 verified against actual asyncpg upsert semantics)
4. `test_passes: test_concurrent_writes.py::test_read_never_sees_partial_write` — a reader loops `asearch` while a concurrent writer does `aput`; all search results for the key are either the complete old version or the complete new version, never a partial (ASSUM-013 verified via Postgres MVCC)
5. `command_runs: python -m pytest tests/integration/ -m integration -v --timeout=120` — the full integration suite (Tasks 10 + 11 + 12) passes with no database or NAS DSN set beyond the ephemeral fixture DSN
6. `command_runs: grep -r "NAS_HOST\|nas_host\|synology\|5432" tests/integration/` — exits 1 (no hardcoded NAS references in integration tests — hermeticity enforced by grep)

**BDD scenarios covered:** "Semantic search can be constrained by metadata filters", "Deleting a memory removes it from retrieval and search", "Concurrent writes to the same key leave one complete winner", "A search during a concurrent write never sees a partial memory"

---

### Task 13 — `assumption_verification_record`

**task_type:** documentation
**complexity:** 1
**dependencies:** `integration_test_suite_store_semantics`, `integration_test_suite_boundary_and_edge`, `unit_test_suite`
**estimated_minutes:** 20
**primary files created/touched:**
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate_assumptions.yaml` (update the three low-confidence entries)

**Acceptance criteria:**
1. `file_exists: features/storage-substrate/storage-substrate_assumptions.yaml` — ASSUM-004 entry updated with `verified_value` field recording the actual asyncpg pool queuing behavior observed in Task 10 acceptance criterion 6
2. Same file — ASSUM-006 entry updated with `verified_value` recording the actual asyncpg connection-timeout duration observed in Task 10 acceptance criterion 5
3. Same file — ASSUM-008 entry updated with `verified_value` recording the actual httpx read-timeout behavior observed in Task 03 acceptance criterion 4
4. Each of the three updated entries has `confidence` field changed from `low` to `verified` and a `verified_by_task` field referencing the task that produced the measurement
5. If any verified value differs from the placeholder default (10, 10 s, 10 s), the corresponding `settings.py` field default is also updated in the same commit to reflect the verified value
6. `command_runs: python -c "import yaml; d = yaml.safe_load(open('features/storage-substrate/storage-substrate_assumptions.yaml')); assert all(a.get('confidence') != 'low' for a in d['assumptions'])"` — exits 0 (no remaining low-confidence items)

**BDD scenarios covered:** "Operations beyond pool capacity queue rather than fail" (ASSUM-004 recorded), "The service refuses to start when the database is unreachable" (ASSUM-006 recorded), "A hung embedding service cannot stall store operations indefinitely" (ASSUM-008 recorded)

---

## Wave Structure

### Wave 1 — Foundation (sequential: all later tasks depend on this)

Tasks: `scaffold_project_layout`

No file conflicts possible; must complete before any other task.

### Wave 2 — Core modules, parallel (no file overlap; all depend only on Wave 1)

Tasks running in parallel:
- `settings_class` — creates `src/fleet_memory/settings.py`, `.env.example`
- `local_ephemeral_compose_and_fixtures` — creates `deploy/local/`, `tests/integration/conftest.py`, `tests/conftest.py`

These touch entirely different file trees. Settings does not import from deploy/; conftest does not import settings directly (it reads env vars).

### Wave 3 — Dependent modules (parallel within wave; each depends on Wave 2 outputs)

Tasks running in parallel:
- `embed_callable` — depends on `settings_class`; creates `src/fleet_memory/embed.py`, `src/fleet_memory/errors.py`
- `nas_deploy_files` — depends on `local_ephemeral_compose_and_fixtures` (for compose conventions); creates `deploy/nas/`

No file conflict: `embed.py` and `deploy/nas/` are in separate trees.

### Wave 4 — Store factory and app shell (sequential within wave due to dependency)

Tasks:
- `store_factory_and_namespace_validation` — depends on `embed_callable` + `settings_class`; must complete before `app_shell_lifespan`
- `app_shell_lifespan` — depends on `store_factory_and_namespace_validation`

These are sequential because `app.py` imports from `store.py`. Within Wave 4, `nas_deploy_operator_handoff` can proceed in parallel with the store work (it is operator time, not AutoBuild time).

### Wave 5 — Test suites (parallel within wave; all depend on Wave 4)

Tasks running in parallel:
- `unit_test_suite` — expands stubs from Tasks 03/05/06; touches only `tests/unit/`
- `integration_test_suite_store_semantics` — touches only `tests/integration/test_store_*.py` and `test_pool_lifecycle.py`

After both complete:
- `integration_test_suite_boundary_and_edge` — depends on store semantics suite (uses same fixtures, avoids conflicts)
- `metadata_filter_and_concurrent_write_integration` — can run in parallel with boundary/edge suite (different test files)

After all integration tests complete:
- `assumption_verification_record` — reads outputs from all test tasks, updates assumptions.yaml

---

## Risks

**R1 — asyncpg pool behavior on overflow may not queue (ASSUM-004 placeholder).** If `asyncpg` raises `asyncpg.pool.PoolTimeout` rather than silently queuing when `pool_max` is saturated, Task 10 AC6 will fail. Mitigation: the verification task (Task 10 AC6) is the detection mechanism; if `PoolTimeout` fires, `pg_pool_max` should be raised or the test rewritten as a timeout-tolerance test with explicit `asyncio.wait_for` wrapping — and the settings default revised. This is a record-and-revise, not a blocking risk.

**R2 — Real nomic over Tailscale may not be reachable in AutoBuild context.** ASSUM-012 confirms integration tests use real nomic. If AutoBuild runs in a network context without Tailscale (e.g. a CI container), the `@pytest.mark.integration` gate will be absent from the default run but the explicit `pytest -m integration` run will fail. Mitigation: the `--marker` exclusion in `pytest.ini` (`addopts = -m "not integration"`) guarantees the default run passes. Integration runs are explicitly operator-or-context-gated. The hermetic correctness AC is satisfied. Document in `pytest.ini` comments that integration tier requires Tailscale access to GB10.

**R3 — `docker-entrypoint-initdb.d` does not re-run if the container has a pre-existing data volume.** If the ephemeral compose fixture leaves a named volume (rather than an anonymous or bind-mount volume), the init script won't fire on subsequent `up` calls, and pgvector may be absent. Mitigation: use anonymous volumes or `docker compose down -v` in the teardown so every test run starts from a blank image. Task 04 AC4 validates this by checking the extension is present after fixture setup.

**R4 — `store.setup()` requires `CREATE EXTENSION` to already exist.** If `AsyncPostgresStore.setup()` is called before `01_extensions.sql` has run (possible if the health check passes before init scripts complete), the setup will fail. Mitigation: the `ephemeral_pg` fixture must wait for the container health check (`pg_isready`) rather than just for the port to open. The `docker-compose.yml` `healthcheck` directive should be set with an appropriate `interval: 2s` and `retries: 10`.

**R5 — `langgraph-checkpoint-postgres` API surface may differ from assumed `index` config shape.** The build plan specifies `{dims: 768, embed: <callable>, fields: ["content"]}` but the actual `AsyncPostgresStore` constructor signature should be verified against the installed package version. If the fields key name or structure differs, `store.py` will fail. Mitigation: Task 05 AC1 verifies the factory can be constructed and `store.setup()` called against the ephemeral instance; a mismatch surfaces immediately in that task.

**R6 — `.env` file loading in `pydantic-settings` may shadow test env vars if `.env` exists in the working directory.** If an operator has a local `.env` with `FLEET_MEMORY_PG_DSN` pointing at the NAS, the integration test fixture's DSN (set via environment variable) may be overridden by the file. Mitigation: the Settings class should use `env_file=".env"` with `env_file_encoding="utf-8"` and pydantic-settings v2 respects env var precedence over `.env` file by default (env vars win); this should be explicitly tested in `test_settings.py::test_env_var_overrides_dotenv`.

---

## Effort & Complexity Summary

| Task | Complexity | Est. Minutes |
|---|---|---|
| 01 scaffold_project_layout | 3 | 40 |
| 02 settings_class | 3 | 35 |
| 03 embed_callable | 4 | 45 |
| 04 local_ephemeral_compose_and_fixtures | 5 | 60 |
| 05 store_factory_and_namespace_validation | 5 | 55 |
| 06 app_shell_lifespan | 4 | 45 |
| 07 nas_deploy_files | 4 | 50 |
| 08 nas_deploy_operator_handoff | 1 | 0 (operator) |
| 09 unit_test_suite | 4 | 60 |
| 10 integration_test_suite_store_semantics | 6 | 90 |
| 11 integration_test_suite_boundary_and_edge | 5 | 70 |
| 12 metadata_filter_and_concurrent_write_integration | 5 | 60 |
| 13 assumption_verification_record | 1 | 20 |

**Total complexity (sum over automatable tasks, excluding operator handoff): 50 / 10 scale = 5.0 average complexity, peak 6**
**Total estimated AutoBuild minutes: 630 minutes = 10.5 hours**
**Operator handoff time (NAS deployment, not in AutoBuild estimate): approximately 30–45 minutes of operator wall-clock time after `nas_deploy_files` lands**

The two longest-running waves (Wave 5 parallel integration tests) account for 220 of those minutes; Wave 2 + Wave 3 in parallel reduce wall-clock to approximately 6.5–7 hours of sequential critical-path time.

---

## Open Items For Implementation

**ASSUM-004 — Connection pool capacity 10, queuing not fail-fast.**
Default encoded as `pg_pool_max: int = 10` in settings. Implementation verifies by running 15 concurrent `aput` calls against a pool of 10. If `asyncpg` raises `asyncpg.pool.PoolTimeout` before all 15 complete, the test must be rewritten to assert the pool raises after an appropriate wait rather than silently queuing, and the setting must be documented as "raises after timeout" not "queues indefinitely". The verified value and asyncpg version are recorded in `storage-substrate_assumptions.yaml` ASSUM-004 `verified_value` field by Task 13.

**ASSUM-006 — Startup fail-fast within 10 seconds.**
Default encoded as `pg_connect_timeout_s: float = 10.0` in settings, passed as `timeout` in the asyncpg pool creation call. Implementation verifies by timing the lifespan entry against a refused port. asyncpg's `pool.create_pool` accepts a `timeout` parameter; the actual observed behavior (does it respect it? does it raise `asyncio.TimeoutError` or `asyncpg.TooManyConnectionsError` or an OS-level connection refused immediately?) is recorded in Task 06 AC4 test file comment and in Task 13.

**ASSUM-008 — Embedding call bounded at 10 seconds.**
Default encoded as `embed_timeout_s: float = 10.0` in settings, passed as `httpx.Timeout(connect=5.0, read=settings.embed_timeout_s)`. Implementation verifies in Task 03 AC4 using a `MockTransport` that never returns a response body and confirming that `httpx` raises `httpx.ReadTimeout` within the configured window. The distinction between `connect` timeout and `read` timeout in httpx must be confirmed — the 10 s bound applies to the read phase (waiting for the embedding model to respond), not merely the TCP connect. Verified value and httpx version recorded in Task 13.

**Additional discovered item — `langgraph-checkpoint-postgres` version pin.**
The package exposing `langgraph.store.postgres.aio.AsyncPostgresStore` is `langgraph-checkpoint-postgres`. At plan time no version constraint is specified in the build plan. `pyproject.toml` should pin a minimum version (e.g. `langgraph-checkpoint-postgres>=2.0`) and Task 05 must confirm the `index` config key name against the installed version's constructor signature. If the `index` parameter shape differs from `{dims, embed, fields}`, this is a breaking discovery that requires a plan amendment before Task 05 can complete.

**Additional discovered item — asyncpg vs psycopg3 under `AsyncPostgresStore`.**
`langgraph-checkpoint-postgres` supports both asyncpg and psycopg3 as backends depending on the DSN scheme (`postgresql+asyncpg://` vs `postgresql://`). The build plan specifies asyncpg implicitly (ASSUM-004 references asyncpg pool). Task 05 must confirm that `AsyncPostgresStore` uses asyncpg when the DSN uses `postgresql+asyncpg://` and that pool-size configuration flows through to the asyncpg pool correctly. The DSN format in settings and `.env.example` must use the `+asyncpg` scheme for all ASSUM-004/006 assumptions to be meaningful.

**Additional discovered item — `store.setup()` idempotency on the ephemeral instance.**
`AsyncPostgresStore.setup()` creates the store schema (tables, indexes). If two test sessions start against the same ephemeral instance (which should not happen given the random project-name isolation, but could happen if the fixture teardown fails), `setup()` must be idempotent. The `IF NOT EXISTS` clause is expected in the LangGraph store DDL but this should be confirmed in Task 10 by running `setup()` twice against the same instance without error.

**Relevant file paths for the implementation agent:**

- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate.feature`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate_assumptions.yaml`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/features/storage-substrate/storage-substrate_summary.md`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/research/ideas/phase-core-build-plan.md`
- `/Users/richardwoollcott/Projects/appmilla_github/fleet-memory/docs/runbooks/RUNBOOK-nas-postgres-deploy.md`
