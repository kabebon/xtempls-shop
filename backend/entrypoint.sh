#!/bin/sh
# Container entrypoint: run migrations ONCE, then start uvicorn.
# Migrations must run before uvicorn forks workers, otherwise each worker
# would try to CREATE TABLE concurrently and crash.
set -e

echo "=== Running database migrations (alembic upgrade head) ==="
alembic upgrade head

echo "=== Starting uvicorn ==="
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
