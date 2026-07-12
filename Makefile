# GridPulse — common developer commands.
# On Windows, run these via Git Bash, or copy the underlying command.

VENV ?= .venv
PY   := $(VENV)/Scripts/python.exe
DBT  := $(VENV)/Scripts/dbt.exe
export GRIDPULSE_DUCKDB := $(CURDIR)/data/electricity_a2.duckdb
export DBT_PROFILES_DIR := $(CURDIR)/dbt

.PHONY: help setup pipeline dbt test dashboard dagster diagram all

help:
	@echo "setup      - create venv and install everything"
	@echo "pipeline   - run ingest -> transform -> load (offline from cache)"
	@echo "dbt        - build dbt models + run all data tests"
	@echo "test       - run the pytest unit suite"
	@echo "dashboard  - launch the Streamlit analytics dashboard"
	@echo "dagster    - launch the Dagster UI (asset lineage + runs)"
	@echo "diagram    - regenerate the architecture diagram"
	@echo "all        - pipeline + dbt + test"

setup:
	py -3.12 -m venv $(VENV)
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[orchestration,transform,dashboard,stream,dev]"
	$(DBT) deps --project-dir dbt

pipeline:
	$(PY) -m gridpulse.pipeline

dbt:
	$(DBT) build --project-dir dbt

test:
	$(PY) -m pytest

dashboard:
	$(VENV)/Scripts/streamlit.exe run dashboard/app_streamlit.py

dagster:
	$(VENV)/Scripts/dagster.exe dev -m orchestration.definitions

diagram:
	$(PY) docs/make_architecture_diagram.py

all: pipeline dbt test
