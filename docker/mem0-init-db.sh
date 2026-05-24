#!/bin/bash
set -e

# Mem0 uses the default postgres database for memory storage and a separate
# application database for users, API keys, request logs, and auth metadata.
APP_DB_NAME="${APP_DB_NAME:-mem0_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
SELECT 'CREATE DATABASE ${APP_DB_NAME}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${APP_DB_NAME}')\gexec
EOSQL
