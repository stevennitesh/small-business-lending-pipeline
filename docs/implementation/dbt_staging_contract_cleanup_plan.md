# Plan: Tighten dbt Staging Contract Documentation

## Goal

Finish the dbt staging subsystem cleanup by documenting and testing the staging handoff contract inside dbt itself.

The staging layer already has the correct local/cloud boundary:

- local route writes DuckDB raw tables and builds dbt with `dev_duckdb`;
- cloud route writes Snowflake raw tables and builds dbt with `prod_snowflake`;
- both routes use the same staging SQL;
- `raw_uri` is the active route-neutral artifact identity;
- `storage_backend` records whether the durable raw artifact is local or S3-backed.

This pass should make that contract obvious in `schema.yml` and enforce the most important identity fields with dbt tests.

## Non-goals

- Do not change staging SQL business logic.
- Do not change model names, raw table names, mart contracts, BI contracts, or Power BI files.
- Do not remove `raw_file_path`, `local_raw_path`, or `s3_raw_uri`; they remain lineage fields for now.
- Do not split staging into separate local and cloud model trees.
- Do not run the heavy full local dbt build unless a compile/test failure requires deeper diagnosis.

## Constraints

- The working tree has an unrelated user-owned `powerbi/lending_dashboard.pbix` change; do not stage or modify it.
- The previous cleanup removed fallback identity logic from staging models and deleted the unused `relation_has_column` macro.
- `RAW_SCHEMA` is the dbt and Snowflake raw schema setting.
- The WSL-safe dbt verification path is `make dbt-local`, which compiles the local dbt graph.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. This is a small docs/tests cleanup in one dbt schema file plus focused tests.

## Acceptance Checks

- `dbt/models/staging/schema.yml` documents `raw_uri`, `storage_backend`, and source lineage fields for staging models that expose them.
- Staging models with source rows have dbt `not_null` tests for `raw_uri`, `storage_backend`, `pipeline_run_id`, and `source_resource_name`.
- `stg_ingestion_manifest` has dbt `not_null` tests for `raw_uri`, `storage_backend`, `pipeline_run_id`, `source_system`, `dataset_name`, and `resource_name`.
- Descriptions make clear that `raw_file_path` / `local_raw_path` / `s3_raw_uri` are lineage fields, not staging join identity.
- Raw source docs use route-neutral wording where possible; `raw_pipeline_run_summary` should not be described as local-only if the current loaders also produce cloud summaries.
- Existing static dbt setup/staging tests are updated to cover the new documented contract.
- Focused tests and dbt compile pass.

## Baseline

- Current source review:
  - `dbt/models/staging/schema.yml` documents business fields but not the lineage fields that now define the handoff contract.
  - `stg_ingestion_manifest` exposes `storage_backend`, `raw_uri`, `local_raw_path`, and `s3_raw_uri`, but only `pipeline_run_id` and `is_latest_successful_snapshot` are documented.
  - SBA, Census, and BLS staging models expose `pipeline_run_id`, source identity fields, `storage_backend`, `raw_uri`, `raw_file_path`, and `sha256_checksum`, but these columns are not documented/tested in `schema.yml`.
  - `dbt/models/sources/sources.yml` describes `raw_pipeline_run_summary` as local DuckDB specific even though route work now treats raw load summaries more generally.
- Baseline checks recently observed:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py` passed.
  - `make dbt-local` passed.
  - `git diff --check` passed.

## Tasks

### Task 1: Document Route-Neutral Lineage Columns

- Outcome: `schema.yml` clearly documents the columns that connect staging rows back to raw load and manifests.
- Builds on or must preserve:
  - existing staging descriptions and data tests;
  - `raw_uri` as active identity;
  - local/cloud shared staging SQL.
- Existing logic to reuse or extend:
  - `dbt/models/staging/schema.yml`
  - `dbt/models/sources/sources.yml`
  - `dbt/models/staging/*/*.sql`
- Public contract or state/data change:
  - Documentation-only for column descriptions.
- Depends on: None.
- Likely files/modules:
  - `dbt/models/staging/schema.yml`
  - `dbt/models/sources/sources.yml`
  - `tests/unit/test_dbt_staging_models.py`
  - `tests/unit/test_dbt_project_setup.py`
- First command/check:
  - `rg -n "raw_uri|storage_backend|raw_file_path|local_raw_path|s3_raw_uri|raw_pipeline_run_summary" dbt/models/staging dbt/models/sources tests/unit`
- Change boundary:
  - Add descriptions for lineage columns. Do not add business transformations.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py`
  - `git diff --check`
- Review focus:
  - Descriptions should distinguish identity from lineage without using old compatibility language.
- Risk/rollback:
  - Low; rollback wording if it confuses route ownership.
- Stop/ask if:
  - The user wants to rename exposed lineage columns instead of only documenting them.
- Status: completed

### Task 2: Add dbt Contract Tests For Staging Identity Fields

- Outcome: dbt enforces the minimum identity fields required for the raw-load to staging handoff.
- Builds on or must preserve:
  - latest-successful snapshot filtering;
  - existing uniqueness and accepted-value tests;
  - static tests that assert staging models require route-neutral identity.
- Existing logic to reuse or extend:
  - `dbt/models/staging/schema.yml`
  - generic dbt `not_null` tests
  - `dbt/tests/assert_staging_sources_latest_snapshots.sql`
- Public contract or state/data change:
  - dbt test failures now flag missing staging identity fields.
- Depends on: Task 1.
- Likely files/modules:
  - `dbt/models/staging/schema.yml`
  - `tests/unit/test_dbt_staging_models.py`
- First command/check:
  - `sed -n '1,220p' dbt/models/staging/schema.yml`
- Change boundary:
  - Add dbt tests only for fields that should always be populated after raw validation/load.
  - Do not add tests for optional lineage fields such as `raw_file_path`, `local_raw_path`, or `s3_raw_uri`.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py`
  - `make dbt-local`
- Review focus:
  - Tests should not accidentally require S3 lineage in the local route or local file lineage in the cloud route.
- Risk/rollback:
  - If full builds expose nulls in fields believed to be required, diagnose upstream raw load rather than weakening the staging contract by default.
- Stop/ask if:
  - Current fixture/raw data intentionally contains null identity values.
- Status: completed

### Task 3: Update Static Tests To Guard The Documented Contract

- Outcome: lightweight unit tests fail if future edits remove the route-neutral staging contract from schema docs/tests.
- Builds on or must preserve:
  - existing static tests in `tests/unit/test_dbt_staging_models.py`;
  - existing project setup tests.
- Existing logic to reuse or extend:
  - YAML parsing in `test_staging_schema_declares_issue_acceptance_tests`.
  - raw source schema assertion in `test_raw_sources_are_documented`.
- Public contract or state/data change:
  - Test-only.
- Depends on: Tasks 1 and 2.
- Likely files/modules:
  - `tests/unit/test_dbt_staging_models.py`
  - `tests/unit/test_dbt_project_setup.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py`
- Change boundary:
  - Keep tests focused on the contract; avoid brittle assertions on every column in every model.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py`
- Review focus:
  - Tests should protect the contract without becoming a second copy of the whole `schema.yml`.
- Risk/rollback:
  - If tests are too brittle, reduce them to required columns and required tests only.
- Stop/ask if:
  - The schema contract is about to be generated rather than hand-maintained.
- Status: completed

## Final Verification

- `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py`
- `make dbt-local`
- `git diff --check`

Optional if recent local raw data is available and WSL has memory headroom:

- `make dbt-build-local-full`

## Open Questions

- Should route-neutral lineage eventually be exposed to Power BI as `raw_uri` only, or should `raw_file_path` remain visible for local troubleshooting?
- Completed in the hard-switch cleanup: `RAW_SCHEMA` is the only raw schema setting.
