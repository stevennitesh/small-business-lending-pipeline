.PHONY: install test runtime-smoke run-local run-cloud dbt-local dbt-compile-local dbt-build-local-full dbt-seed-local cleanup-local-data-dry-run cleanup-local-data powerbi-model-check

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
PREFECT_HOME ?= .tmp/prefect
export PREFECT_HOME
DBT_PROFILES_TMP ?= .tmp/dbt_profiles

$(PREFECT_HOME):
	mkdir -p $(PREFECT_HOME)

$(DBT_PROFILES_TMP)/profiles.yml: dbt/profiles.yml.example
	mkdir -p $(DBT_PROFILES_TMP)
	cp dbt/profiles.yml.example $(DBT_PROFILES_TMP)/profiles.yml

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

run-cloud: $(PREFECT_HOME) $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_cloud_pipeline.sh

dbt-local: dbt-compile-local

dbt-compile-local: $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_dbt_local.sh compile

dbt-build-local-full: $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_dbt_local.sh build

dbt-seed-local: $(DBT_PROFILES_TMP)/profiles.yml
	cd dbt && DBT_PROFILES_DIR=../$(DBT_PROFILES_TMP) ../$(VENV)/bin/dbt seed --target dev_duckdb

cleanup-local-data-dry-run:
	$(VENV_PYTHON) scripts/cleanup_local_data.py --dry-run

cleanup-local-data:
	$(VENV_PYTHON) scripts/cleanup_local_data.py --apply

powerbi-model-check:
	$(VENV_PYTHON) scripts/validate_powerbi_model.py
