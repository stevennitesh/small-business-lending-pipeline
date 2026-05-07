#!/usr/bin/env bash
set -euo pipefail

DBT_BIN="${DBT_BIN:-../.venv/bin/dbt}"

cd dbt
export DBT_PROFILES_DIR="${DBT_PROFILES_DIR:-../.tmp/dbt_profiles}"
"$DBT_BIN" build --target dev_duckdb "$@"
