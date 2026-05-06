#!/usr/bin/env bash
set -euo pipefail

cd dbt
dbt build --target dev_duckdb "$@"
