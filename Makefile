.PHONY: install test runtime-smoke run-local run-local-fixture run-local-live run-cloud benchmark-local dbt-local dbt-compile-local dbt-build-local-fast dbt-build-local-full dbt-seed-local powerbi-refresh-local cleanup-local-data-dry-run cleanup-local-data powerbi-model-check

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

run-local: run-local-fixture

run-local-fixture: $(PREFECT_HOME)
	scripts/run_local_pipeline.sh --extract-mode fixture

run-local-live: $(PREFECT_HOME)
	scripts/run_local_pipeline.sh --extract-mode live

run-cloud: $(PREFECT_HOME) $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_cloud_pipeline.sh

benchmark-local:
	@test -n "$(COMMAND)" || { echo 'Set COMMAND="make dbt-local" or another local command to benchmark.'; exit 2; }
	$(VENV_PYTHON) scripts/benchmark_local_command.py --command "$(COMMAND)"

dbt-local: dbt-compile-local

dbt-compile-local: $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_dbt_local.sh compile

dbt-build-local-full: $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_dbt_local.sh build

dbt-build-local-fast:
	@echo 'dbt-build-local-fast is reserved for the fast dbt quality mode implemented in issue #94.'
	@exit 2

dbt-seed-local: $(DBT_PROFILES_TMP)/profiles.yml
	cd dbt && DBT_PROFILES_DIR=../$(DBT_PROFILES_TMP) ../$(VENV)/bin/dbt seed --target dev_duckdb

powerbi-refresh-local:
	@echo 'powerbi-refresh-local is reserved for the fast Power BI refresh command implemented in issue #95.'
	@exit 2

cleanup-local-data-dry-run:
	$(VENV_PYTHON) scripts/cleanup_local_data.py --dry-run

cleanup-local-data:
	$(VENV_PYTHON) scripts/cleanup_local_data.py --apply

powerbi-model-check:
	$(VENV_PYTHON) scripts/validate_powerbi_model.py
