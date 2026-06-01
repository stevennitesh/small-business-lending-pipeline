# Plan: Safe Switch To Local And Cloud Routes

## Goal

Make the current local/cloud route design self-sufficient before deleting old cloud-route compatibility paths.

The target runtime shape is:

- `local`: source extracts -> local raw artifacts -> raw validation -> DuckDB raw tables -> dbt `dev_duckdb` -> local Power BI CSV exports.
- `cloud`: source extracts -> S3 raw artifacts -> raw validation from S3 -> Snowflake raw tables -> dbt `prod_snowflake` -> Snowflake BI schema.

This plan prepares the repo so the new method works without depending on the old local-file-to-Snowflake fallback. The old public cloud-route aliases and compatibility files have since been removed.

## Non-goals

- Do not remove compatibility paths in this slice.
- Do not change KPI definitions or BI table semantics.
- Do not remove DuckDB; it remains the local warehouse.
- Do not require live AWS or Snowflake credentials for default unit tests.
- Do not redesign extraction beyond the minimum needed to make cloud raw loading independent of local raw files.

## Constraints

- Keep the repo runnable after each task.
- Preserve local route behavior throughout the switch.
- Cloud route must not require durable local raw files.
- Raw artifacts remain immutable and traceable through manifests.
- dbt should use the same logical model design on DuckDB and Snowflake.
- Tests must use mocks/fakes where live cloud credentials are unavailable.

## Execution Mode

Execution mode: sequential.

Parallel groups:

- None. The work changes shared route contracts, raw metadata, Snowflake loading, and dbt joins, so sequential implementation is safer.

## Baseline

- Working tree: clean on `master` before this plan was written.
- Current route behavior:
  - `local` and `cloud` are canonical run modes.
  - `cloud` is the canonical cloud route.
- Current hidden dependency:
  - dbt staging models still join raw source rows to manifests with `raw.raw_file_path = manifest.local_raw_path`.
  - `dim_source_file` keys source files by `local_raw_path`.
  - Snowflake S3 `COPY INTO` assumes raw tables already exist and can ingest source files directly from S3.
  - The older Python connector Snowflake loader can still auto-create enriched raw tables from local files.
- Relevant checks:
  - `make test`
  - `make dbt-local` for lightweight local dbt compile verification.
  - `make dbt-build-local-full` only when an explicit full live-data DuckDB build is needed and WSL has enough memory headroom.
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/unit/test_snowflake_loader.py tests/integration/test_duckdb_loader.py`
  - `git diff --check`

## Acceptance Checks

- Local route still passes focused flow and DuckDB loader tests.
- `make dbt-local` compiles after dbt joins move to route-neutral raw identity.
- The explicit full local build remains available as `make dbt-build-local-full`.
- Cloud route tests prove raw artifacts are S3-backed and Snowflake raw loading does not use local raw paths.
- Snowflake loader tests prove a fresh fake Snowflake warehouse can create/load required raw tables from S3-oriented inputs.
- Run summaries and docs clearly identify `local` and `cloud` routes.
- Active implementation paths no longer depend on old cloud-route aliases or local files as Snowflake inputs.

## Tasks

## GitHub Issues

1. [#47 Make route vocabulary internally cloud-named](https://github.com/stevennitesh/small-business-lending-pipeline/issues/47)
2. [#48 Promote raw_uri to active raw identity](https://github.com/stevennitesh/small-business-lending-pipeline/issues/48)
3. [#49 Make Snowflake cloud raw load self-sufficient](https://github.com/stevennitesh/small-business-lending-pipeline/issues/49)
4. [#50 Tighten cloud flow guards around local raw paths](https://github.com/stevennitesh/small-business-lending-pipeline/issues/50)
5. [#51 Mark old route compatibility paths inactive](https://github.com/stevennitesh/small-business-lending-pipeline/issues/51)

### Task 1: Make Route Vocabulary Internally Cloud-Named

- Outcome: Internal code uses `cloud` naming for the cloud route.
- Builds on or must preserve: `RUN_MODE_ALIASES`, `CLOUD_FLOW_STAGES`, `make run-cloud`.
- Existing logic to reuse or extend: `LocalRunContext.is_cloud_route` and `context.stage_order`.
- Public contract or state/data change: `cloud` is the only accepted cloud route name.
- Depends on: none.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_prefect_local_flow.py`
  - `README.md`
- Change boundary:
  - Rename internal cloud checks and stage names from old cloud-route language where safe.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py`
- Review focus:
  - No route behavior changes beyond terminology.
  - `run_mode` in summaries remains `cloud` after normalization.
- Risk/rollback:
  - Low risk; revert renames if tests show stage-order drift.
- Stop/ask if:
  - A current user-facing command still depends on an old cloud-route alias.
- Status: pending.

### Task 2: Promote `raw_uri` To The Active Raw Identity

- Outcome: Raw source tables, manifests, dbt staging joins, source-file dimensions, and facts use route-neutral `raw_uri` as the active artifact identity.
- Builds on or must preserve:
  - `ExtractionManifest.raw_uri`
  - `ExtractionManifest.storage_backend`
  - local manifests where `raw_uri == local_raw_path`
  - S3 manifests where `raw_uri == s3_raw_uri`
- Existing logic to reuse or extend:
  - `pipelines/utils/manifest.py`
  - `pipelines/load/raw_load_common.py`
  - `dbt/models/staging/audit/stg_ingestion_manifest.sql`
- Public contract or state/data change:
  - New raw table rows should include `raw_uri` and `storage_backend`.
  - `raw_file_path` may remain temporarily as a legacy alias, but dbt joins should stop depending on it.
- Depends on: Task 1.
- Likely files/modules:
  - `pipelines/load/raw_load_common.py`
  - `pipelines/load/duckdb_loader.py`
  - `pipelines/load/snowflake_loader.py`
  - `dbt/models/staging/sba/stg_sba_7a_loans.sql`
  - `dbt/models/staging/sba/stg_sba_504_loans.sql`
  - `dbt/models/staging/census/stg_census_bds_state_year.sql`
  - `dbt/models/staging/bls/stg_bls_laus_state_month.sql`
  - `dbt/models/marts/dimensions/dim_source_file.sql`
  - `dbt/models/marts/facts/fact_sba_loans.sql`
  - `dbt/models/marts/facts/fact_bds_state_year.sql`
  - `dbt/models/marts/facts/fact_laus_state_month.sql`
  - `dbt/models/sources/sources.yml`
  - loader/dbt tests
- Change boundary:
  - Add `raw_uri` and `storage_backend` metadata to raw source rows.
  - Join raw source rows to manifests on `raw_uri`.
  - Use `raw_uri` for source-file keys.
  - Keep `raw_file_path` as a temporary compatibility column when local files exist.
- Verification command:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py tests/unit/test_dbt_bi_pipeline_models.py`
  - `make dbt-local`
- Review focus:
  - dbt no longer requires `manifest.local_raw_path` for new rows.
  - Existing local route still produces the same BI row counts and non-empty BI tables.
- Risk/rollback:
  - Medium risk because source-file keys can shift. Roll back to local-path joins if dbt reconciliation tests fail, then split key migration into a smaller slice.
- Stop/ask if:
  - A downstream Power BI contract explicitly requires `raw_file_path` rather than a route-neutral source artifact field.
- Status: pending.

### Task 3: Make Snowflake Cloud Raw Load Self-Sufficient

- Outcome: The cloud route can create/load Snowflake raw tables from S3-backed artifacts.
- Builds on or must preserve:
  - `load_raw_extracts_to_snowflake_from_s3`
  - `RawArtifactLocation.storage_backend == "s3"`
  - Snowflake schemas `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `BI`, `AUDIT`
- Existing logic to reuse or extend:
  - `pipelines/load/snowflake_loader.py`
  - `pipelines/load/raw_load_common.py`
  - existing fake Snowflake cursor tests
- Public contract or state/data change:
  - Cloud raw load should create required raw tables or landing tables before loading.
  - Loaded raw rows must include `pipeline_run_id`, source identity, `ingestion_date`, `raw_uri`, `storage_backend`, `s3_raw_uri`, and `sha256_checksum`.
  - The raw load summary should continue to report table row counts and `load_pattern = "s3_stage_copy"` or a more accurate cloud-native name.
- Depends on: Task 2.
- Likely files/modules:
  - `pipelines/load/snowflake_loader.py`
  - `pipelines/load/raw_load_common.py`
  - `tests/unit/test_snowflake_loader.py`
  - `tests/unit/test_prefect_local_flow.py`
- Change boundary:
  - Keep active cloud loading on the S3-stage Snowflake loader.
  - Add explicit Snowflake raw table setup for S3 loads.
  - For CSV and JSON source artifacts, choose one consistent cloud load strategy:
    - create typed/variant landing tables and insert enriched rows into final raw tables; or
    - write warehouse-ready raw-row artifacts during extraction and `COPY INTO` those row artifacts.
  - Keep the old fallback function untouched for now, but unused by the cloud flow.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - No source group can silently load from a local raw path in cloud mode.
  - Fresh fake Snowflake state is enough for the S3 load path to create/load tables.
  - JSON sources are handled intentionally, not accidentally passed through a CSV-only path.
- Risk/rollback:
  - High risk. If Snowflake `COPY INTO` for JSON raw payloads becomes too large for this slice, choose warehouse-ready raw-row artifacts as the smaller controllable path.
- Stop/ask if:
  - The implementation needs a live Snowflake-only behavior that cannot be represented with fake cursor tests.
- Status: pending.

### Task 4: Tighten Cloud Flow Guards Around Local Raw Paths

- Outcome: Cloud route fails clearly if any required cloud raw manifest is local-backed or missing `raw_uri`.
- Builds on or must preserve:
  - `check_raw_manifest`
  - `RawArtifactReader`
  - `validate_raw_outputs`
- Existing logic to reuse or extend:
  - `pipelines/validation/raw_manifest_artifact_validation.py`
  - source-specific payload check modules under `pipelines/validation/`
  - cloud flow tests in `tests/unit/test_prefect_local_flow.py`
- Public contract or state/data change:
  - Cloud route requires S3-backed raw manifests for source data.
  - Local route continues to allow local-backed manifests.
- Depends on: Tasks 2 and 3.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `pipelines/validation/raw_manifest_artifact_validation.py`
  - `tests/unit/test_raw_validation_flow.py`
  - `tests/unit/test_raw_validation_manifest_failures.py`
  - `tests/unit/test_raw_manifest_storage_checks.py`
  - `tests/unit/test_prefect_local_flow.py`
- Change boundary:
  - Add route-aware validation expectations for storage backend.
  - Make failures blocking and human-readable.
  - Do not reject local manifests in fixture/local mode.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_flow.py tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_manifest_storage_checks.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - The guard catches mixed local/S3 cloud manifests before Snowflake load starts.
  - The guard does not make local development require AWS.
- Risk/rollback:
  - Medium risk if fixture paths are accidentally treated as cloud paths.
- Stop/ask if:
  - Any planned demo flow intentionally mixes local raw files with cloud Snowflake loading.
- Status: pending.

### Task 5: Mark Old Compatibility Paths As Inactive But Not Deleted

- Outcome: Old paths remain available for rollback, but tests and docs show they are no longer the active implementation path.
- Builds on or must preserve:
  - The user wants deletion to happen later after the safe switch works.
  - Old cloud-route wrappers may remain as compatibility commands for now.
- Existing logic to reuse or extend:
  - README runtime route section.
  - implementation docs.
  - tests that cover `run-cloud`.
- Public contract or state/data change:
  - No public removal yet.
  - Docs should say `run-cloud` is canonical.
  - Any old fallback function should be documented as compatibility-only, not the main cloud path.
- Depends on: Tasks 1-4.
- Likely files/modules:
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
  - `docs/implementation/two_route_safe_hard_switch_plan.md`
  - `tests/test_repository_skeleton.py`
  - `tests/unit/test_s3_loader.py`
  - `tests/unit/test_snowflake_loader.py`
- Change boundary:
  - Update docs and tests to prefer `cloud`.
  - Keep old files/functions in place until the follow-up deletion issue.
- Verification command:
  - `.venv/bin/python -m pytest tests/test_repository_skeleton.py tests/unit/test_s3_loader.py tests/unit/test_snowflake_loader.py`
- Review focus:
  - No active code path points users toward local files as Snowflake inputs.
  - Compatibility is still intact until explicitly removed.
- Risk/rollback:
  - Low risk.
- Stop/ask if:
  - The cleanup starts deleting old files or rejecting `final` before the user approves the deletion phase.
- Status: pending.

## Final Verification

Run after all tasks:

```bash
.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/unit/test_raw_validation_flow.py tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_manifest_storage_checks.py tests/unit/test_snowflake_loader.py tests/integration/test_duckdb_loader.py
make dbt-local
make test
git diff --check
```

Optional live/cloud verification when credentials are available:

```bash
make run-cloud
```

The live cloud check is stronger evidence than fake Snowflake/S3 tests, but it should not be required for default local development.

## Follow-Up Deletion Plan

Only after this plan passes:

- Completed separately: remove old cloud-route aliases, wrapper scripts, and compatibility tests.
- Completed separately: remove the old local-file Snowflake loader if no tests or rollback docs still require it.
- Remove legacy `raw_file_path` / `local_raw_path` dependencies from dbt outputs if Power BI and docs no longer need them.

## Open Questions

- Should the cloud raw load use Snowflake landing tables over source payloads, or should extraction emit warehouse-ready raw-row artifacts to S3 for `COPY INTO`?
- Should Power BI expose a route-neutral source artifact field named `raw_uri`, or keep a legacy `raw_file_path` column for user familiarity?
- Once the safe switch passes, should old compatibility deletion be one GitHub issue or split into route alias removal and loader fallback removal?
