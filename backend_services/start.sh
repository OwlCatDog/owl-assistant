#!/usr/bin/env sh
set -eu

exec uvicorn main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8080}"
