# Plan: Clean Up dbt Staging Handoff Contract

## Goal

Make the raw-load to dbt-staging handoff clearer and stricter now that the local and cloud routes share the same raw identity contract.

The intended contract is:

- Local route: DuckDB raw tables, `storage_backend = 'local'`, route-neutral `raw_uri`, dbt target `dev_duckdb`.
- Cloud route: Snowflake raw tables loaded from S3, `storage_backend = 's3'`, route-neutral `raw_uri`, dbt target `prod_snowflake`.
- dbt staging models should use the same source contract for both routes and should not depend on local-only path fields for row identity.

## Non-goals

- Do not change raw table names, staging model names, mart model names, BI table contracts, or Power BI fields in this cleanup.
- Do not redesign dbt environments or introduce separate local/cloud staging models.
- Do not remove `raw_file_path`, `local_raw_path`, or `s3_raw_uri` lineage fields from outputs yet.
- Do not run the heavy full local dbt build unless explicitly needed; use the WSL-safe dbt compile path first.
- Do not touch generated warehouse files, local data, dbt `target/`, or the Power BI `.pbix`.

## Constraints

- The working tree currently has an unrelated user-owned `powerbi/lending_dashboard.pbix` change; implementation must not stage or modify it.
- Raw loaders now populate `raw_uri` and `storage_backend` for local DuckDB and cloud Snowflake rows.
- Staging models already join raw rows to manifests by `pipeline_run_id`, `source_resource_name`, and `raw_uri`.
- dbt should remain target-driven: route differences belong in profiles, raw-load code, and warehouse configuration, not duplicated staging SQL.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. The cleanup touches shared dbt source configuration and staging model contracts, so sequential implementation is safer.

## Acceptance Checks

- dbt raw source schema configuration uses route-neutral vocabulary rather than a Snowflake-specific env var for both routes.
- Existing cloud smoke variables continue to work during a transition, or docs call out the required env var change clearly.
- Staging models require `raw_uri` and `storage_backend` from raw tables instead of silently falling back to local-only identity fields.
- Manifest staging continues to expose `local_raw_path`, `s3_raw_uri`, `raw_uri`, and `storage_backend` as lineage fields.
- Staging source rows still join only to latest successful manifests.
- Focused dbt compile and staging tests pass.

## Baseline

- Working tree:
  - `powerbi/lending_dashboard.pbix` is modified and should be treated as user-owned.
- Current behavior:
  - `dbt/models/sources/sources.yml` uses `SNOWFLAKE_RAW_SCHEMA` with default `raw` for the raw source schema.
  - `stg_ingestion_manifest` checks whether `storage_backend` and `raw_uri` columns exist, then falls back to deriving them from legacy manifest path fields.
  - SBA, Census, and BLS staging models check whether source raw tables have `raw_uri` and `storage_backend`, then fall back to `raw_file_path` and `'local'`.
  - Staging rows join to `stg_ingestion_manifest` using `pipeline_run_id`, source resource, and `raw_uri`.
- Relevant source/tests:
  - `dbt/models/sources/sources.yml`
  - `dbt/models/staging/audit/stg_ingestion_manifest.sql`
  - `dbt/models/staging/sba/stg_sba_7a_loans.sql`
  - `dbt/models/staging/sba/stg_sba_504_loans.sql`
  - `dbt/models/staging/census/stg_census_bds_state_year.sql`
  - `dbt/models/staging/bls/stg_bls_laus_state_month.sql`
  - `dbt/tests/assert_staging_sources_latest_snapshots.sql`
  - `tests/unit/test_dbt_staging_models.py`
  - `README.md`
- Baseline checks already observed:
  - `make dbt-local` passed with target `dev_duckdb`.
  - `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py` passed.

## Tasks

### Task 1: Rename Raw Source Schema Configuration

- Outcome: dbt source configuration uses a route-neutral schema env var.
- Builds on or must preserve:
  - local default raw schema remains `raw`;
  - cloud route can still point dbt at the configured Snowflake raw schema.
- Existing logic to reuse or extend:
  - `dbt/models/sources/sources.yml`
  - `README.md` cloud smoke examples
  - `pipelines/load/snowflake_loader.py` raw schema env behavior
- Public contract or state/data change:
  - Prefer `RAW_SCHEMA` for dbt source configuration.
  - Keep `SNOWFLAKE_RAW_SCHEMA` as a documented fallback if needed to avoid breaking existing `.env` files immediately.
- Depends on: None.
- Likely files/modules:
  - `dbt/models/sources/sources.yml`
  - `README.md`
  - `.env.example`
  - tests that assert dbt profile or source configuration, if present.
- First command/check:
  - `rg -n "SNOWFLAKE_RAW_SCHEMA|RAW_SCHEMA" dbt README.md .env.example tests pipelines`
- Change boundary:
  - Rename or add the dbt-facing env var only; do not change Snowflake loader schema creation semantics unless needed for consistency.
- Verification command:
  - `make dbt-local`
  - `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py`
- Review focus:
  - Local route should not require a Snowflake-named env var.
  - Existing cloud setup should have a clear migration path.
- Risk/rollback:
  - Main risk is breaking existing `.env` cloud smoke examples. Keep fallback support or update docs/tests in the same slice.
- Stop/ask if:
  - The user wants to preserve `SNOWFLAKE_RAW_SCHEMA` as the only public env var for Snowflake demos.
- Status: completed

### Task 2: Make Manifest Staging Require Active Identity Columns

- Outcome: `stg_ingestion_manifest` trusts the current raw-load manifest contract instead of deriving active identity from legacy path fields.
- Builds on or must preserve:
  - `raw_uri` remains the canonical manifest identity;
  - `storage_backend` remains visible for local/cloud lineage;
  - `local_raw_path` and `s3_raw_uri` remain exposed as lineage fields.
- Existing logic to reuse or extend:
  - `stg_ingestion_manifest`
  - `pipelines/utils/manifest.py`
  - raw validation checks requiring `raw_uri`.
- Public contract or state/data change:
  - Missing `raw_uri` or `storage_backend` in raw manifests becomes a dbt compile/run failure instead of silent fallback.
- Depends on: Task 1 only if tests or docs are touched there; otherwise independent.
- Likely files/modules:
  - `dbt/models/staging/audit/stg_ingestion_manifest.sql`
  - `dbt/models/staging/schema.yml`
  - `tests/unit/test_dbt_staging_models.py`
- First command/check:
  - `rg -n "relation_has_column\\(|coalesce\\(nullif\\(local_raw_path|s3_raw_uri.*storage_backend" dbt/models/staging tests`
- Change boundary:
  - Remove only the manifest identity fallback logic. Do not remove lineage columns.
- Verification command:
  - `make dbt-local`
  - `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py`
- Review focus:
  - dbt should fail loudly if upstream raw-load contract is broken.
- Risk/rollback:
  - If any current fixture raw database was built before the new contract, it may need to be regenerated instead of supported forever.
- Stop/ask if:
  - There is a deliberate need to run dbt against old raw databases generated before the local/cloud route refactor.
- Status: completed

### Task 3: Remove Raw Source Row Fallbacks From Staging Models

- Outcome: SBA, Census, and BLS staging models use required `raw.raw_uri` and `raw.storage_backend` directly.
- Builds on or must preserve:
  - current joins to latest successful manifests;
  - staged row counts and KPI outputs;
  - `raw_file_path` as a lineage field, not an identity fallback.
- Existing logic to reuse or extend:
  - `stg_sba_7a_loans`
  - `stg_sba_504_loans`
  - `stg_census_bds_state_year`
  - `stg_bls_laus_state_month`
  - `assert_staging_sources_latest_snapshots.sql`
- Public contract or state/data change:
  - Raw source tables must include `raw_uri` and `storage_backend`.
  - Staging model row identity no longer has a local-only fallback.
- Depends on: Task 2.
- Likely files/modules:
  - `dbt/models/staging/sba/stg_sba_7a_loans.sql`
  - `dbt/models/staging/sba/stg_sba_504_loans.sql`
  - `dbt/models/staging/census/stg_census_bds_state_year.sql`
  - `dbt/models/staging/bls/stg_bls_laus_state_month.sql`
  - `tests/unit/test_dbt_staging_models.py`
- First command/check:
  - `rg -n "has_raw_uri|has_storage_backend|artifact_raw_uri|artifact_storage_backend" dbt/models/staging`
- Change boundary:
  - Remove compatibility branching only; preserve parsing, field standardization, latest-manifest filtering, and source identity filters.
- Verification command:
  - `make dbt-local`
  - `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py`
- Review focus:
  - No model should join raw source rows to manifests using `raw_file_path`.
- Risk/rollback:
  - If local dbt compile/run fails due to an old raw database schema, regenerate raw tables with the current local route rather than reintroducing fallback behavior.
- Stop/ask if:
  - A recruiter demo or saved local artifact must run against pre-refactor raw tables.
- Status: completed

### Task 4: Document The Staging Handoff Contract

- Outcome: docs explain that dbt staging is intentionally shared between local and cloud routes, while route differences live in raw load and dbt target/profile configuration.
- Builds on or must preserve:
  - README local/cloud route sections.
  - current implementation docs describing local and cloud pipeline ownership.
- Existing logic to reuse or extend:
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
  - this plan document.
- Public contract or state/data change:
  - Documentation-only.
- Depends on: Tasks 1-3.
- Likely files/modules:
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
  - `docs/implementation/dbt_staging_handoff_cleanup_plan.md`
- First command/check:
  - `rg -n "raw_uri|storage_backend|SNOWFLAKE_RAW_SCHEMA|RAW_SCHEMA|dbt target" README.md docs/implementation`
- Change boundary:
  - Keep docs short; do not rewrite historical plans except to add a concise current-state note if needed.
- Verification command:
  - `git diff --check`
- Review focus:
  - A reader should understand why there is one staging layer for both routes.
- Risk/rollback:
  - Low; rollback wording if it overstates tested cloud behavior.
- Stop/ask if:
  - The user wants the plan converted into GitHub issues before documentation updates.
- Status: completed

## Final Verification

- `make dbt-local`
- `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_dbt_staging_models.py`
- Optional after local raw tables are regenerated with the current contract:
  - `make dbt-build-local-full`
- Optional cloud verification when credentials and Snowflake resources are ready:
  - `scripts/run_cloud_pipeline.sh --extract-mode fixture`
  - or dbt build/compile against `prod_snowflake` with isolated smoke schemas.
- `git diff --check`

## Decisions

- `SNOWFLAKE_RAW_SCHEMA` remains as a transition fallback, while `RAW_SCHEMA` is the preferred dbt-facing raw schema setting.
- `raw_file_path` remains visible as local lineage, but `raw_uri` is the active route-neutral artifact identity.
