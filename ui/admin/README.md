# TotalRecall Admin UI

Static TypeScript UI for catalogue review, memory deletion, learning review, and
feature flag visibility.

The UI calls only backend HTTP APIs:

- `GET /v1/catalogue`
- `GET /v1/catalogue/{entity_id}`
- `DELETE /v1/memories/{entity_id}`
- `GET /v1/learning/runs`
- `POST /v1/learning/runs`
- `POST /v1/learning/runs/{run_id}/approve/{discovery_id}`
- `POST /v1/learning/runs/{run_id}/reject/{discovery_id}`
- `GET /v1/flags`
- `GET /v1/metrics`

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
