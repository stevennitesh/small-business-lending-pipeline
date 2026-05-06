#!/usr/bin/env bash
set -euo pipefail

python -m pipelines.flows.lending_pipeline_flow \
  --run-mode local \
  --dbt-target dev_duckdb \
  "$@"
