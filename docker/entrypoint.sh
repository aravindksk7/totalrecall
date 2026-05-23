#!/bin/sh
set -eu

run_migrations() {
  uv run python -m totalrecall.storage.migrations
}

uvicorn_reload_args=""
if [ "${TOTALRECALL_UVICORN_RELOAD:-false}" = "true" ]; then
  uvicorn_reload_args="--reload"
fi

case "${1:-api}" in
  api)
    if [ "${TOTALRECALL_RUN_MIGRATIONS_ON_STARTUP:-false}" = "true" ]; then
      run_migrations
    fi
    exec uv run uvicorn totalrecall.main:app \
      --host "${HOST:-0.0.0.0}" \
      --port "${PORT:-8000}" \
      ${uvicorn_reload_args}
    ;;
  memory-wrapper)
    if [ "${TOTALRECALL_RUN_MIGRATIONS_ON_STARTUP:-false}" = "true" ]; then
      run_migrations
    fi
    exec uv run uvicorn totalrecall.memory.service_app:app \
      --host "${HOST:-0.0.0.0}" \
      --port "${PORT:-8001}" \
      ${uvicorn_reload_args}
    ;;
  migrate)
    run_migrations
    ;;
  test)
    shift
    run_migrations
    exec uv run pytest "$@"
    ;;
  pytest)
    run_migrations
    exec uv run "$@"
    ;;
  uv)
    if [ "${2:-}" = "run" ] && [ "${3:-}" = "pytest" ]; then
      run_migrations
    fi
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
