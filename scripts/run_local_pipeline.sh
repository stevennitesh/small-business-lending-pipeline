#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi
export PREFECT_HOME="${PREFECT_HOME:-.tmp/prefect}"
mkdir -p "$PREFECT_HOME"

"$PYTHON_BIN" -m pipelines.flows.lending_pipeline_flow \
  --run-mode local \
  --dbt-target dev_duckdb \
  "$@"
