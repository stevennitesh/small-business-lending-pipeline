.PHONY: install test runtime-smoke run-local dbt-local

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
export PREFECT_HOME ?= .tmp/prefect

$(PREFECT_HOME):
	mkdir -p $(PREFECT_HOME)

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

test:
	$(VENV_PYTHON) -m pytest

runtime-smoke: $(PREFECT_HOME)
	$(VENV_PYTHON) -c "import boto3, duckdb, pandas, prefect, requests, snowflake.connector, yaml; import dbt.cli.main"

run-local: $(PREFECT_HOME)
	scripts/run_local_pipeline.sh

dbt-local:
	scripts/run_dbt_local.sh
