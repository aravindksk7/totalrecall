# TotalRecall

TotalRecall is a Context-Driven Test Architect for AI-assisted test automation.

## Phase 1 Foundation

Accepted implementation defaults:

- Python 3.14+
- `uv` for package and lock management
- FastAPI backend
- Local Postgres governance store
- Config-backed feature flags
- Environment/local-secret-backed credential provider
- MVP auth, tenant context, and RBAC from the first APIs
- In-process memory wrapper for MVP

## Docker Test Path

Run the Phase 1 verification path with Docker Compose:

```powershell
docker compose run --build --rm test
```

The app container waits for Postgres, applies SQL migrations, and runs the test suite.

## Local API

Start the API with Docker Compose:

```powershell
docker compose up app
```

Health endpoint:

```text
GET /health
```

Protected identity endpoint:

```text
GET /v1/whoami
Authorization: Bearer dev-token
```

## Detailed Setup And Usage

See `docs/setup-and-usage.md` for step-by-step local setup, Docker startup,
environment configuration, API examples, memory-wrapper usage, Mem0 setup,
admin UI usage, CLI commands, testing, and troubleshooting.
