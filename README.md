# TotalRecall

TotalRecall is a context-driven AI test automation service. It helps teams
generate test cases and test automation artifacts while controlling context
growth, token usage, memory governance, and framework-specific testing
knowledge.

The project separates reusable automation skills from dynamic application
memory:

- Static skills live in the Skill Registry, for example Playwright TypeScript
  and Pytest conventions.
- Dynamic application knowledge lives behind a TotalRecall memory wrapper, with
  Mem0 available as a long-term memory adapter.
- Catalogue, tombstones, audit events, context snapshots, learning runs, and
  governance metadata live in local Postgres.
- The generation pipeline plans only the relevant context before calling an LLM
  provider.

## What TotalRecall Does

- Generates test automation artifacts from a structured request.
- Generates structured test case packs from prompts, JIRA stories, RAG guidance,
  and selected test types.
- Selects relevant framework skills and dynamic memories before prompt
  creation.
- Supports memory search, upsert, get, delete, tombstone filtering, and
  capabilities checks through a stable wrapper contract.
- Uses a provider gateway so upstream code does not depend directly on one LLM
  provider.
- Provides catalogue and learning APIs so teams can inspect, learn, approve,
  reject, and unlearn knowledge.
- Adds guardrails, secret redaction, validation, repair hooks, metrics, and
  audit events around generation.

## Architecture At A Glance

Main runtime:

- Python 3.14+
- FastAPI
- Postgres with pgvector support
- `uv` for Python dependency and lockfile management
- File-backed skill definitions
- In-process memory wrapper by default
- Optional standalone memory-wrapper service
- Optional TypeScript Playwright validation worker
- Static admin UI under `ui/admin`

Important modules:

```text
totalrecall/
  api/                FastAPI dependencies and routes
  auth/               bearer-token auth, tenant context, RBAC
  cache/              TTL cache for memory search results
  catalogue/          catalogue contracts
  cli/                command-line client
  config/             settings, feature flags, credentials
  context/            context planner and token budget metadata
  generation/         generation request models and orchestrator
  learning/           controlled repository learning pipeline
  memory/             wrapper and adapters, including Mem0 v1
  metadata/           deterministic metadata extraction
  observability/      request IDs and in-process metrics
  prompts/            prompt builder, redaction, repair prompts
  providers/          provider gateway, stub, local, OpenAI adapter
  skills/             skill models and registry
  storage/            Postgres migrations and repositories
  testgen/            JIRA, RAG, guardrails, routing, test case packs
  validation/         artifact validation and Playwright worker client
```

## Prerequisites

Install the following for the recommended Docker path:

- Docker Desktop with Docker Compose
- Git

Install these for local development without Docker:

- Python 3.14 or newer
- `uv`
- Node.js 20 or newer, only if rebuilding the admin UI or Playwright worker

The Docker path is the simplest way to start because it builds the Python
runtime, starts Postgres, applies migrations, and runs in the same shape as the
test container.

## Step 1: Clone The Repository

```powershell
git clone https://github.com/aravindksk7/totalrecall.git
cd totalrecall
```

## Step 2: Start The API With Docker

Start the main API and Postgres:

```powershell
docker compose up --build app
```

This starts:

- Postgres on `localhost:5432`
- A one-shot `migrate` container that applies SQL migrations
- TotalRecall API on `http://localhost:8000`

The app container waits for Postgres and the migration job before it starts
Uvicorn. The development override also enables Uvicorn reload for mounted source
files.

Verify health:

```powershell
curl.exe http://localhost:8000/health
```

Verify authenticated access:

```powershell
curl.exe -H "Authorization: Bearer dev-token" http://localhost:8000/v1/whoami
```

Expected response:

```json
{
  "tenant_id": "tenant_dev",
  "actor_id": "dev-user",
  "roles": ["admin"]
}
```

OpenAPI docs:

```text
http://localhost:8000/docs
```

## Step 3: Start All Local Services

To start the main API, standalone memory wrapper, and Docker-served admin UI:

```powershell
docker compose up --build app memory-wrapper admin-ui
```

Service URLs:

- Main API: `http://localhost:8000`
- Main API docs: `http://localhost:8000/docs`
- Memory wrapper API: `http://localhost:8001`
- Memory wrapper docs: `http://localhost:8001/docs`
- Admin UI: `http://localhost:4173`
- Admin UI proxied API base: `http://localhost:4173/v1`

When you use the Docker-served admin UI, set the UI API Base to
`http://localhost:4173/v1`. Nginx serves the static UI and proxies `/v1/*` and
`/health` to the main API container, so browser requests stay on the same
origin.

The default Docker configuration uses the deterministic stub memory adapter:

```json
{
  "memory.adapter": "stub",
  "memory.write_enabled": true,
  "memory.fail_open_on_search": true
}
```

## Step 4: Configure Local Environment Variables

For non-Docker runs, copy the template:

```powershell
Copy-Item .env.example .env
```

Important settings:

```text
TOTALRECALL_DATABASE_URL=postgresql://totalrecall:totalrecall@localhost:5432/totalrecall
TOTALRECALL_AUTH_TOKENS={"dev-token":{"tenant_id":"tenant_dev","actor_id":"dev-user","roles":["admin"]}}
TOTALRECALL_FEATURE_FLAGS={"memory.adapter":"stub","memory.write_enabled":true,"memory.fail_open_on_search":true}
TOTALRECALL_CREDENTIAL_REFS={}
TOTALRECALL_SKILLS_DIR=skills
```

Built-in role intent:

- `reader`: read catalogue and basic service information.
- `generator`: generation access.
- `maintainer`: generation, memory write, and learning promotion.
- `admin`: full local permissions, including memory delete and skill publish.

Use unique bearer tokens per tenant or actor in real deployments. Do not commit
real tokens or provider API keys.

## Step 5: Run Locally Without Docker

Install Python dependencies:

```powershell
uv sync --dev --frozen
```

Start only Postgres with Docker:

```powershell
docker compose up -d postgres
```

Set local environment variables for the current PowerShell session:

```powershell
$env:TOTALRECALL_ENVIRONMENT = "development"
$env:TOTALRECALL_DATABASE_URL = "postgresql://totalrecall:totalrecall@localhost:5432/totalrecall"
$env:TOTALRECALL_AUTH_TOKENS = '{"dev-token":{"tenant_id":"tenant_dev","actor_id":"dev-user","roles":["admin"]}}'
$env:TOTALRECALL_FEATURE_FLAGS = '{"memory.adapter":"stub","memory.write_enabled":true,"memory.fail_open_on_search":true}'
```

Apply migrations:

```powershell
uv run python -m totalrecall.storage.migrations
```

Start the main API:

```powershell
uv run uvicorn totalrecall.main:app --host 0.0.0.0 --port 8000 --reload
```

Optionally start the standalone memory wrapper in another terminal:

```powershell
uv run uvicorn totalrecall.memory.service_app:app --host 0.0.0.0 --port 8001 --reload
```

## Step 6: Use The Main API

The examples below use the development token from `docker-compose.yml`.

```powershell
$headers = @{
  Authorization = "Bearer dev-token"
  "Content-Type" = "application/json"
}
```

### Check Identity

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8000/v1/whoami
```

### View Feature Flags

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8000/v1/flags
```

### View Metrics

```powershell
Invoke-RestMethod http://localhost:8000/v1/metrics
```

### View Monitoring Summary

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8000/v1/monitoring/summary
```

The monitoring summary includes memory health, Mem0 readiness, memory operation
counters, provider registration and credential status, and the latest
token-efficiency snapshot from context planning.

## Step 7: Generate Test Automation Artifacts

The default provider is `stub`, so this works without an external LLM key.

```powershell
$body = @{
  tenant_id = "tenant_dev"
  application_id = "app_demo"
  prompt = "Create Playwright tests for a login form with valid and invalid credentials."
  target = @{
    language = "typescript"
    framework = "playwright"
    pattern = "pom"
    locator_strategy = "page_file"
  }
  scope = @{
    domain = "auth"
    route = "/login"
    tags = @("smoke", "login")
  }
  provider = @{
    provider_id = "stub"
    model = "stub"
  }
  options = @{
    validate = $true
    allow_repair = $false
    max_input_tokens = 12000
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/generations `
  -Body $body
```

The response includes:

- `request_id`
- `status`
- generated `artifacts`
- `validation`
- `context.skill_ids`
- `context.memory_ids`
- estimated input tokens

## Step 8: Generate A Test Case Pack

TotalRecall also supports a feature-gated test case generation path. This path
is activated when `jira_key` or `test_types` is included in the generation
request.

Supported test types:

- `functional`
- `negative`
- `edge_case`
- `api`
- `regression`

Example:

```powershell
$body = @{
  tenant_id = "tenant_dev"
  application_id = "app_demo"
  prompt = "Generate negative and edge case test cases for login validation."
  jira_key = "SCRUM-5"
  test_types = @("negative", "edge_case")
  target = @{
    language = "typescript"
    framework = "playwright"
    pattern = "pom"
    locator_strategy = "page_file"
  }
  scope = @{
    domain = "auth"
    route = "/login"
  }
  provider = @{
    provider_id = "stub"
    model = "stub"
  }
  options = @{
    validate = $false
    allow_repair = $false
    max_input_tokens = 12000
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/generations `
  -Body $body
```

When configured with real adapters, this path can combine:

- Reformulated intent
- JIRA story and acceptance criteria
- RAG guidance from pgvector
- selected test type sections
- output guardrails
- optional tone refinement
- test case pack normalization

## Step 9: Enable JIRA, RAG, Guardrails, And Tone Check

These features are controlled through `TOTALRECALL_FEATURE_FLAGS`.

Example with local stub-style feature flags:

```powershell
$env:TOTALRECALL_FEATURE_FLAGS = '{
  "memory.adapter":"stub",
  "reformulator.adapter":"keyword",
  "jira.enabled":true,
  "jira.adapter":"stub",
  "rag.enabled":true,
  "rag.adapter":"stub",
  "guardrails.input_enabled":true,
  "guardrails.output_enabled":true,
  "tone_check.enabled":false
}'
```

For JIRA Cloud, configure:

- `jira.enabled=true`
- `jira.adapter=cloud`
- `jira.base_url`
- `jira.email`
- credential ref `jira_api_token`

For pgvector RAG, configure:

- `rag.enabled=true`
- `rag.adapter=pgvector`
- `rag.dsn`
- credential ref `openai_api_key` if using `OpenAIEmbedder`

## Step 10: Use The Catalogue

Search catalogue entries:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri "http://localhost:8000/v1/catalogue?application_id=app_demo&limit=20"
```

Filter by category or status:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri "http://localhost:8000/v1/catalogue?category=dynamic_memory&status=active"
```

Get one entry:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8000/v1/catalogue/<entity_id>
```

## Step 11: Delete Or Tombstone Memory

The main API memory delete route writes a tombstone to Postgres, updates the
in-memory tombstone filter, records an audit event, and invalidates memory
search cache entries for the tenant and application.

```powershell
$body = @{
  application_id = "app_demo"
  reason = "No longer relevant"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Delete `
  -Headers $headers `
  -Uri http://localhost:8000/v1/memories/<entity_id> `
  -Body $body
```

## Step 12: Use The Standalone Memory Wrapper

The standalone memory wrapper exposes memory operations on port `8001`. It uses
the same auth tokens, feature flags, credential provider, cache, and tombstone
filtering model as the main API.

Health:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

Capabilities:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8001/v1/memory/capabilities
```

Upsert memory:

```powershell
$body = @{
  memory = @{
    entity_id = "mem_login_001"
    tenant_id = "tenant_dev"
    application_id = "app_demo"
    summary = "Login smoke test pattern"
    knowledge = "Use stable role-based locators and assert successful navigation after submit."
    tags = @{
      domain = "auth"
      framework = "playwright"
    }
    confidence = 0.95
    status = "active"
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8001/v1/memory/upsert `
  -Body $body
```

Search memory:

```powershell
$body = @{
  tenant_id = "tenant_dev"
  application_id = "app_demo"
  query = "login"
  filters = @{ domain = "auth" }
  limit = 10
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8001/v1/memory/search `
  -Body $body
```

Get memory:

```powershell
$body = @{
  tenant_id = "tenant_dev"
  application_id = "app_demo"
  entity_id = "mem_login_001"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8001/v1/memory/get `
  -Body $body
```

Delete memory through the wrapper:

```powershell
$body = @{
  tenant_id = "tenant_dev"
  application_id = "app_demo"
  entity_id = "mem_login_001"
  deleted_by = "dev-user"
  reason = "Demo cleanup"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8001/v1/memory/delete `
  -Body $body
```

## Step 13: Enable Mem0

The default memory adapter is `stub`. To use Mem0, configure a credential
reference and switch the adapter:

```powershell
$env:MEM0_API_KEY = "<your-mem0-api-key>"
$env:MEM0_HOST = "http://localhost:8888"
$env:TOTALRECALL_CREDENTIAL_REFS = '{"mem0_api_key":"env:MEM0_API_KEY","mem0_host":"env:MEM0_HOST"}'
$env:TOTALRECALL_FEATURE_FLAGS = '{"memory.adapter":"mem0_v1","memory.write_enabled":true,"memory.fail_open_on_search":true}'
```

Use `mem0_host` only for self-hosted Mem0. Leave it unset for hosted Mem0.
Restart the app or memory wrapper after changing environment variables.

With the Docker-served admin UI, you can do the same for local development from
the `Credentials` view:

1. Open the `Mem0 Setup` panel.
2. Paste the Mem0 API key generated by the Mem0 dashboard setup wizard or
   bootstrap flow.
3. For self-hosted Mem0, enter the REST API host reachable from the
   TotalRecall API process. Use `http://localhost:8888` for local Python, or
   `http://host.docker.internal:8888` when TotalRecall runs in Docker and Mem0
   runs on the host. Leave this blank for hosted Mem0.
4. Keep `Activate Mem0 for TotalRecall memory after saving` checked.
5. Click `Configure Mem0`.

The UI writes `local-secrets/mem0_api_key`, optionally writes
`local-secrets/mem0_host`, and applies runtime flags for `memory.adapter=mem0_v1`,
`memory.write_enabled=true`, and `memory.fail_open_on_search=true`. Saved local
credentials are ignored by Git and shared with the Docker app and memory wrapper
through the `local-secrets` bind mount.

### Run TotalRecall With Self-Hosted Mem0

Use the optional `docker-compose.mem0.yml` overlay when you want Mem0 to run as
part of the TotalRecall Docker stack. The overlay starts a separate `mem0` REST
API container and a `mem0-postgres` pgvector container, then points the
TotalRecall API and memory wrapper at `http://mem0:8000` on the internal Docker
network. The Mem0 API image is built from the official Mem0 source tarball by
default because the published `mem0/mem0-api-server:latest` image may not
publish a compatible manifest for every local Docker platform. Mem0 stores
vector data in the `mem0-postgres-data` Docker volume and its local history
SQLite database in the `mem0-history-data` Docker volume mounted at
`/app/history`.

```powershell
$env:OPENAI_API_KEY = "<provider-key-used-by-mem0>"
$env:MEM0_ADMIN_API_KEY = "<long-random-mem0-admin-api-key>"
$env:MEM0_JWT_SECRET = "<long-random-jwt-secret>"

docker compose `
  -f docker-compose.yml `
  -f docker-compose.mem0.yml `
  up --build app memory-wrapper admin-ui mem0
```

The host URLs are:

- TotalRecall API: `http://localhost:8000`
- TotalRecall Admin UI: `http://localhost:4173`
- Mem0 REST API: `http://localhost:8888`

Inside Docker, TotalRecall uses:

```text
TOTALRECALL_FEATURE_FLAGS={"memory.adapter":"mem0_v1","memory.write_enabled":true,"memory.fail_open_on_search":true}
TOTALRECALL_CREDENTIAL_REFS={"mem0_api_key":"env:MEM0_API_KEY","mem0_host":"env:MEM0_HOST"}
MEM0_API_KEY=$MEM0_ADMIN_API_KEY
MEM0_HOST=http://mem0:8000
```

For local development with the repo hot-reload overrides, include the override
file explicitly:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.override.yml `
  -f docker-compose.mem0.yml `
  up --build app memory-wrapper admin-ui mem0
```

Mem0 auth is enabled by default. The overlay uses `MEM0_ADMIN_API_KEY` as the
programmatic key for TotalRecall, while `MEM0_JWT_SECRET` signs Mem0 auth
tokens. Replace both values for any shared or production environment.
When `mem0_host` is configured, TotalRecall calls the Mem0 OSS REST endpoints
with `X-API-Key`; hosted Mem0 continues to use the Mem0 Platform SDK default.

If you previously saved `local-secrets/mem0_api_key` or
`local-secrets/mem0_host` from the Admin UI, those local credentials can take
precedence over environment references. Reconfigure the `Mem0 Setup` panel or
delete the saved local values before validating the Docker overlay.

### Start Self-Hosted Mem0 From Admin UI

The `Credentials` view includes a `Self-hosted Mem0 Docker` panel that accepts:

- `OPENAI_API_KEY`
- `MEM0_ADMIN_API_KEY`
- `MEM0_JWT_SECRET`
- Mem0 host for TotalRecall, usually `http://mem0:8000` when TotalRecall runs in
  Docker on the same Compose network, or `http://localhost:8888` for local
  Python.

Submitting the panel saves the values to ignored local secret files, writes
`local-secrets/mem0-selfhost.env`, saves `mem0_api_key`, `mem0_host`,
`mem0_jwt_secret`, and `openai_api_key`, and activates the `mem0_v1` memory
adapter when requested. The API response never returns the submitted secret
values.

Docker startup from the Admin UI is disabled by default. Enable it only on a
trusted local developer machine:

```powershell
$env:TOTALRECALL_ADMIN_DOCKER_CONTROL_ENABLED = "true"
$env:TOTALRECALL_DOCKER_COMPOSE_PROJECT_DIR = "C:\totalrecall"
```

When enabled, the backend runs:

```text
docker compose --env-file local-secrets/mem0-selfhost.env -f docker-compose.yml -f docker-compose.mem0.yml up -d mem0 mem0-postgres
```

If TotalRecall itself is running inside a container, API-side Docker startup
also requires a Docker CLI and host Docker socket/project path access inside
that API container. The simpler local path is to run the API from the repo root
or start Mem0 with the documented Compose command.

If Docker reports `no matching manifest for linux/amd64` for
`mem0/mem0-api-server:latest`, rebuild with the current overlay. It uses
[docker/mem0-api.Dockerfile](/c:/totalrecall/docker/mem0-api.Dockerfile) and:

```text
MEM0_REF=main
MEM0_HISTORY_DB_PATH=/app/history/history.db
MEM0_API_IMAGE=totalrecall-mem0-api-server:latest
```

Supported credential reference formats:

- `env:MEM0_API_KEY`
- `env:MEM0_HOST`
- `local:mem0_api_key`
- `local:mem0_host`
- `file:/absolute/path/to/secret`
- `cloud:mem0_api_key`
- `external:mem0_api_key`

External credential adapter contract:

```text
GET {TOTALRECALL_EXTERNAL_CREDENTIAL_BASE_URL}/secrets/{secret_name}
```

The response may be JSON:

```json
{"value": "secret-value"}
```

or plaintext containing the secret value.

## Step 14: Run Learning Discovery

Learning scans an approved local path and creates discoveries that can be
approved, rejected, or promoted to catalogue entries.

With Docker, use a path visible inside the container. With local Python, use a
host path.

For Docker on Windows, host paths such as `C:\ENV\test-env-management\tests`
are not visible inside the API container unless they are mounted. Configure a
workspace mount and path mapping before starting the stack:

```powershell
$env:TOTALRECALL_LEARNING_WORKSPACE_HOST = "C:\ENV"
$env:TOTALRECALL_LEARNING_PATH_MAPPINGS = '{"C:\\ENV":"/learning-workspace"}'
docker compose up --build app memory-wrapper admin-ui
```

Then either submit the host path:

```text
C:\ENV\test-env-management\tests
```

or submit the container path directly:

```text
/learning-workspace/test-env-management/tests
```

The Admin UI now shows learning run warnings, including missing-path and
path-mapping messages, in the Learning view.

```powershell
$body = @{
  application_id = "app_demo"
  scope = @{
    repository = "local"
    branch = "main"
    path = "/app/tests"
    framework = "playwright"
    domain = "auth"
  }
  trigger_type = "manual"
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/learning/runs `
  -Body $body
```

List learning runs:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri "http://localhost:8000/v1/learning/runs?application_id=app_demo"
```

Show a run:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8000/v1/learning/runs/<run_id>
```

Approve a discovery:

```powershell
$body = @{ reason = "Useful reusable pattern" } | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/learning/runs/<run_id>/approve/<discovery_id> `
  -Body $body
```

Reject a discovery:

```powershell
$body = @{ reason = "Duplicate or low value" } | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/learning/runs/<run_id>/reject/<discovery_id> `
  -Body $body
```

### Search Discoveries And Bulk Approve/Reject

Search across all discoveries for the tenant with optional filters:

```powershell
# Search for pending discoveries about login, with high confidence
Invoke-RestMethod `
  -Headers $headers `
  -Uri "http://localhost:8000/v1/learning/discoveries?q=login&status=discovered&confidence_min=0.7&limit=50"
```

Query parameters:

| Parameter | Description |
|-----------|-------------|
| `q` | Text search on the discovery summary (case-insensitive substring) |
| `status` | Filter by status: `discovered`, `approved`, `rejected`, `promoted` |
| `discovery_type` | Filter by type: `static_skill_candidate`, `dynamic_memory`, `catalogue_reference` |
| `confidence_min` | Minimum confidence threshold (0.0–1.0) |
| `run_id` | Restrict to a specific learning run |
| `limit` | Maximum results (1–200, default 50) |

Bulk approve a selection:

```powershell
$body = @{
  discovery_ids = @("disc_001", "disc_002", "disc_003")
  reason        = "Batch approval after sprint review"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/learning/discoveries/bulk-approve `
  -Body $body
```

Bulk reject a selection:

```powershell
$body = @{
  discovery_ids = @("disc_004", "disc_005")
  reason        = "Outside scope for this release"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/learning/discoveries/bulk-reject `
  -Body $body
```

Both bulk endpoints return:

```json
{ "processed": 2, "skipped": 1, "discovery_ids": ["disc_001", "disc_002"] }
```

`processed` — discoveries successfully updated; `skipped` — already processed
or not found. Bulk approve also promotes eligible `static_skill_candidate`
discoveries to the catalogue, same as single approve.

**Admin UI**: The Learning section now has a collapsible **Search & Bulk
Actions** panel. Filter by summary text, status, type, and confidence;
select individual rows with checkboxes or use Select All; then click **Bulk
Approve** or **Bulk Reject** to process the selection in one request.

## Step 15: Govern Skills

List loaded skills:

```powershell
Invoke-RestMethod `
  -Headers $headers `
  -Uri http://localhost:8000/v1/skills
```

Promote a skill:

```powershell
$body = @{ notes = "Approved for local use" } | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/skills/<skill_id>/promote `
  -Body $body
```

Deprecate a skill:

```powershell
$body = @{ notes = "Replaced by newer guidance" } | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Headers $headers `
  -Uri http://localhost:8000/v1/skills/<skill_id>/deprecate `
  -Body $body
```

## Step 16: Use The Admin UI

The admin UI is static and lives under `ui/admin`.

Start the Docker-served UI with the API:

```powershell
docker compose up --build app admin-ui
```

Open:

```text
http://localhost:4173
```

Use these connection values:

```text
API Base: http://localhost:4173/v1
Token: dev-token
Tenant ID: tenant_dev
Application ID: app_demo
```

The `Generate` view can submit a prompt directly to `/v1/generations`. Optional
fields such as JIRA key and requested test types let the backend orchestrator
pull JIRA context, retrieve RAG guidance, select skills and memories, run
guardrails, call the configured provider, and return artifacts or a test case
pack in one flow.

The `Credentials` view can save local runtime credential values for Mem0,
OpenAI, Claude/Anthropic, Gemini, local LLM endpoints, and JIRA. Values are
written under the ignored `local-secrets` directory and are not returned by the
API after saving. Select `Apply linked runtime defaults` when saving
`mem0_api_key` to switch the runtime memory adapter to `mem0_v1`.

The `Monitoring` view shows operational status for memory and Mem0, memory
operation counters, provider registration/credential readiness, and the latest
token-efficiency snapshot from generation context planning. Use the refresh
control or auto-refresh selector when validating runtime memory/provider setup.

You can also serve the static files directly without Docker:

```powershell
cd ui/admin
python -m http.server 4173
```

Open:

```text
http://localhost:4173
```

Use these connection values:

```text
API Base: http://localhost:8000/v1
Token: dev-token
Tenant ID: tenant_dev
Application ID: app_demo
```

The checked-in `ui/admin/dist/app.js` keeps the UI runnable without a Node
toolchain. If you edit `ui/admin/src/app.ts` or `ui/admin/src/styles.css`,
rebuild it:

```powershell
cd ui/admin
npm install
npm run build
```

Browser calls from `http://localhost:4173` and `http://127.0.0.1:4173` are
allowed by default through `TOTALRECALL_CORS_ALLOWED_ORIGINS`. If you serve the
admin UI from a different host or port, add that origin to the setting before
starting the API.

## Step 17: Use The CLI

Set connection variables:

```powershell
$env:TOTALRECALL_URL = "http://localhost:8000"
$env:TOTALRECALL_TOKEN = "dev-token"
```

Show help:

```powershell
uv run totalrecall --help
```

Search catalogue:

```powershell
uv run totalrecall catalogue search --application-id app_demo --output json
```

Get a catalogue entry:

```powershell
uv run totalrecall catalogue get <entity_id> --output json
```

Tombstone a memory entry:

```powershell
uv run totalrecall catalogue delete-memory <entity_id> `
  --application-id app_demo `
  --reason "No longer relevant" `
  --yes
```

Run learning:

```powershell
uv run totalrecall learn run `
  --application-id app_demo `
  --path C:\totalrecall\tests `
  --repository local `
  --branch main `
  --framework playwright `
  --domain auth `
  --output json
```

List learning runs:

```powershell
uv run totalrecall learn list --application-id app_demo --output json
```

Show a learning run:

```powershell
uv run totalrecall learn show <run_id> --output json
```

For full generation request control, use `POST /v1/generations` directly.

## Step 18: Run Tests And Checks

Run the full Docker test path:

```powershell
docker compose run --build --rm test
```

Run tests locally after starting Postgres:

```powershell
$env:TOTALRECALL_RUN_DATABASE_TESTS = "1"
uv run python -m totalrecall.storage.migrations
uv run pytest
```

Run lint checks:

```powershell
uv run ruff check .
```

Run focused memory wrapper tests:

```powershell
docker compose run --build --rm test test `
  tests/unit/test_mem0_adapter.py `
  tests/contract/test_mem0_wrapper_contract.py `
  tests/contract/test_memory_wrapper.py
```

## Common Operations

Stop services:

```powershell
docker compose down
```

Stop services and remove the local Postgres volume:

```powershell
docker compose down -v
```

Rebuild after dependency changes:

```powershell
docker compose build --no-cache app migrate test memory-wrapper
```

Run migrations manually:

```powershell
docker compose run --rm migrate
```

Inspect logs:

```powershell
docker compose logs -f app
docker compose logs -f memory-wrapper
docker compose logs -f migrate
docker compose logs -f admin-ui
docker compose logs -f postgres
```

## Troubleshooting

### Docker Cannot Connect To The Daemon

Start Docker Desktop, wait for it to finish initializing, then rerun the command.

### Health Endpoint Fails

Check service logs:

```powershell
docker compose logs app
docker compose logs postgres
```

Common causes:

- Postgres is not healthy yet.
- Migrations failed.
- `TOTALRECALL_DATABASE_URL` points to the wrong host.

### Auth Returns 401

Confirm the request includes:

```text
Authorization: Bearer dev-token
```

Also confirm `TOTALRECALL_AUTH_TOKENS` contains the token.

### Tenant Mismatch Returns 403

The `tenant_id` in the request body must match the authenticated token tenant.
For the default Docker token, use:

```text
tenant_dev
```

### Database Endpoints Return 503

Start Postgres and set:

```text
TOTALRECALL_ENABLE_DATABASE=true
```

### Mem0 Adapter Is Unavailable Or Inactive

The Mem0 adapter is registered by the app, but it is only active when
`memory.adapter` is set to `mem0_v1` and a `mem0_api_key` credential can be
resolved.

Confirm:

```text
TOTALRECALL_FEATURE_FLAGS={"memory.adapter":"mem0_v1"}
TOTALRECALL_CREDENTIAL_REFS={"mem0_api_key":"env:MEM0_API_KEY","mem0_host":"env:MEM0_HOST"}
MEM0_API_KEY=<your key>
MEM0_HOST=http://localhost:8888
```

For Docker/local development you can also save `mem0_api_key` in the Admin UI
`Credentials` view and check `Apply linked runtime defaults`, or run the
`docker-compose.mem0.yml` overlay to provision a self-hosted Mem0 REST API.
Use the `Monitoring` view to confirm `mem0.status`, credential and host
configuration, SDK availability, write-enabled state, and fail-open state.

### Learning Run Finds No Files

Make sure `scope.path` exists from the service process. In Docker, host paths
must be mounted into the container before the service can scan them.

### Admin UI Cannot Call The API

For direct API calls from the browser, confirm:

- API Base is `http://localhost:8000/v1` or the proxied
  `http://localhost:4173/v1`.
- Bearer token is set to the development token `dev-token`.
- `TOTALRECALL_CORS_ALLOWED_ORIGINS` includes the UI origin when using a custom
  host or port.

The browser sends an `OPTIONS` preflight for authenticated calls because the UI
uses the `Authorization` header. The API should answer that preflight with
`200` for allowed origins.

## Security Notes

- Do not commit `.env`, local secret files, Mem0 keys, OpenAI keys, JIRA API
  tokens, or production bearer tokens.
- Use credential references such as `env:`, `file:`, `local:`, `cloud:`, or
  `external:` instead of hardcoded values.
- Keep memory deletion and learning promotion behind roles with the required
  permissions.
- Treat the stub provider and development token as local-only defaults.
