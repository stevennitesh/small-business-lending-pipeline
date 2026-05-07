#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
exec "$PYTHON_BIN" -m pipelines.load.snowflake_loader "$@"
