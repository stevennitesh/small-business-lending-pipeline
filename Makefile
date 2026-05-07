.PHONY: install test runtime-smoke run-local run-final dbt-local dbt-seed-local powerbi-model-check

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

run-final: $(PREFECT_HOME) $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_final_pipeline.sh

dbt-local: $(DBT_PROFILES_TMP)/profiles.yml
	scripts/run_dbt_local.sh

dbt-seed-local: $(DBT_PROFILES_TMP)/profiles.yml
	cd dbt && DBT_PROFILES_DIR=../$(DBT_PROFILES_TMP) ../$(VENV)/bin/dbt seed --target dev_duckdb

powerbi-model-check:
	$(VENV_PYTHON) scripts/validate_powerbi_model.py
