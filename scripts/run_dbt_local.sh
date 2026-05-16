#!/usr/bin/env bash
set -euo pipefail

DBT_BIN="${DBT_BIN:-../.venv/bin/dbt}"
DBT_LOCAL_COMMAND="${1:-compile}"

if [[ $# -gt 0 ]]; then
  shift
fi

cd dbt
export DBT_PROFILES_DIR="${DBT_PROFILES_DIR:-../.tmp/dbt_profiles}"
"$DBT_BIN" "$DBT_LOCAL_COMMAND" --target dev_duckdb "$@"
