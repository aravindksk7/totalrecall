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
- TotalRecall API on `http://localhost:8000`

The app container waits for Postgres, applies SQL migrations, then starts
Uvicorn.

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

To start the main API and standalone memory wrapper together:

```powershell
docker compose up --build app memory-wrapper
```

Service URLs:

- Main API: `http://localhost:8000`
- Main API docs: `http://localhost:8000/docs`
- Memory wrapper API: `http://localhost:8001`
- Memory wrapper docs: `http://localhost:8001/docs`

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
$env:TOTALRECALL_CREDENTIAL_REFS = '{"mem0_api_key":"env:MEM0_API_KEY"}'
$env:TOTALRECALL_FEATURE_FLAGS = '{"memory.adapter":"mem0_v1","memory.write_enabled":true,"memory.fail_open_on_search":true}'
```

Restart the app or memory wrapper after changing feature flags.

Supported credential reference formats:

- `env:MEM0_API_KEY`
- `local:mem0_api_key`
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

Serve it locally:

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

The backend does not currently enable browser CORS by default. If browser calls
from `localhost:4173` to `localhost:8000` are blocked, use OpenAPI docs, the
CLI, or serve the UI and API behind the same origin.

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
docker compose run --build --rm test uv run pytest `
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
docker compose build --no-cache app test memory-wrapper
```

Inspect logs:

```powershell
docker compose logs -f app
docker compose logs -f memory-wrapper
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

### Mem0 Adapter Is Not Available

The Mem0 adapter is registered only when `TOTALRECALL_CREDENTIAL_REFS` includes
`mem0_api_key`.

Confirm:

```text
TOTALRECALL_FEATURE_FLAGS={"memory.adapter":"mem0_v1"}
TOTALRECALL_CREDENTIAL_REFS={"mem0_api_key":"env:MEM0_API_KEY"}
MEM0_API_KEY=<your key>
```

Restart the app after changing those values.

### Learning Run Finds No Files

Make sure `scope.path` exists from the service process. In Docker, host paths
must be mounted into the container before the service can scan them.

### Admin UI Cannot Call The API

The backend currently does not install CORS middleware by default. Use OpenAPI
docs at `http://localhost:8000/docs`, use the CLI, or serve the UI and API from
the same origin.

## Security Notes

- Do not commit `.env`, local secret files, Mem0 keys, OpenAI keys, JIRA API
  tokens, or production bearer tokens.
- Use credential references such as `env:`, `file:`, `local:`, `cloud:`, or
  `external:` instead of hardcoded values.
- Keep memory deletion and learning promotion behind roles with the required
  permissions.
- Treat the stub provider and development token as local-only defaults.
