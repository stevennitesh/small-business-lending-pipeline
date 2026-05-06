.PHONY: install test run-local dbt-local

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

test:
	$(VENV_PYTHON) -m pytest

run-local:
	$(VENV_PYTHON) -m pipelines.flows.lending_pipeline_flow --run-mode local --dbt-target dev_duckdb

dbt-local:
	cd dbt && dbt build --target dev_duckdb
