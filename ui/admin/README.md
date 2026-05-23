# TotalRecall Admin UI

Static TypeScript UI for prompt orchestration, runtime provider credentials,
Mem0 and provider monitoring, catalogue review, memory deletion, learning
review, and feature flag visibility.

The UI calls only backend HTTP APIs:

- `GET /v1/catalogue`
- `GET /v1/catalogue/{entity_id}`
- `POST /v1/generations`
- `GET /v1/credentials`
- `PUT /v1/credentials/{credential_key}`
- `DELETE /v1/credentials/{credential_key}`
- `GET /v1/monitoring/summary`
- `GET /v1/monitoring/memory`
- `GET /v1/monitoring/providers`
- `GET /v1/monitoring/token-efficiency`
- `DELETE /v1/memories/{entity_id}`
- `GET /v1/learning/runs`
- `POST /v1/learning/runs`
- `POST /v1/learning/runs/{run_id}/approve/{discovery_id}`
- `POST /v1/learning/runs/{run_id}/reject/{discovery_id}`
- `GET /v1/flags`
- `GET /v1/metrics`

## Connection

When the Docker stack is running, use either API base:

```text
http://localhost:4173/v1
http://localhost:8000/v1
```

Use the local development bearer token:

```text
dev-token
```

`localhost:4173` is allowed by the API CORS defaults. If you serve the UI from a
different origin, add that origin to `TOTALRECALL_CORS_ALLOWED_ORIGINS`.

## Monitoring

The Monitoring view shows:

- Overall API health
- Active and configured memory adapter
- Mem0 credential, SDK, write, and fail-open status
- Memory search/get/upsert/delete counters and latency averages
- Provider registration, credential readiness, and health
- Latest context-planning token-efficiency values

Open `index.html` directly or serve the directory:

```bash
python -m http.server 4173
```

Build from TypeScript when the frontend toolchain is installed:

```bash
npm install
npm run build
```

The checked-in `dist/app.js` keeps the UI runnable in Python-only development
and CI environments.
