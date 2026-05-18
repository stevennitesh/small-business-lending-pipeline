# Plan: Separate Local and Cloud Pipeline Routes

## Goal

Make the project clearly support two intentional execution routes:

1. Local route for development, testing, debugging, and Power BI prototyping on one machine.
2. Cloud route for production-style raw landing, warehouse loading, dbt modeling, and BI consumption without relying on local raw files as the warehouse input.

The recruiter-facing story should be simple: the pipeline is proven locally first with DuckDB, then promoted to a cloud architecture using S3 as raw object storage, Snowflake as the cloud warehouse, and dbt as the transformation and quality layer.

## Current Reality

The repo now has active local and cloud route stage lists in `pipelines/flows/lending_pipeline_flow.py`. The older `final` run-mode alias and wrapper script have been removed; `cloud` is the public cloud route name.

Local mode currently does this:

```text
source extracts -> local raw files -> raw validation -> DuckDB raw tables -> dbt dev_duckdb -> local BI CSV exports
```

Cloud mode is intended to do this:

```text
source extracts -> S3 raw landing zone -> raw validation -> Snowflake raw load from S3
             -> dbt prod_snowflake -> Snowflake BI tables
```

The active cloud route makes S3 the cloud raw landing owner and makes Snowflake load from S3-backed manifests. The older local-file Snowflake connector path has been removed so Snowflake raw loading now means S3-stage cloud loading.

## Target Architecture

### Local Route

Purpose: fast local development and verification.

```text
Public sources
  -> local raw files
  -> local manifests and validation results
  -> DuckDB raw schema
  -> dbt target: dev_duckdb
  -> DuckDB staging/marts/BI/audit schemas
  -> local Power BI export CSVs
```

Ownership:

- Local filesystem owns raw snapshots for development.
- DuckDB owns local SQL tables.
- dbt owns all transformations and tests.
- Power BI can consume local exports while the dashboard is being designed.

### Cloud Route

Purpose: production-style portfolio architecture.

```text
Public sources
  -> S3 raw landing zone
  -> S3 manifests and validation results
  -> Snowflake stage / COPY INTO raw schema
  -> dbt target: prod_snowflake
  -> Snowflake staging/marts/BI/audit schemas
  -> Power BI direct connection to Snowflake BI schema
```

Ownership:

- S3 owns immutable raw source files and pipeline artifacts.
- Snowflake owns queryable raw, staging, mart, BI, and audit tables.
- dbt owns transformations, lineage, documentation, and tests.
- Power BI consumes only modeled BI or mart tables, never raw files.

## Non-goals

- Do not add Glue, Lambda, Step Functions, Athena, Redshift, Spark, or Terraform for the MVP.
- Do not remove DuckDB; it remains the local warehouse.
- Do not make Power BI consume raw files.
- Do not move KPI logic into Python, Snowflake worksheets, or Power BI measures when it belongs in dbt.
- Do not require cloud credentials for default local tests.

## Required Changes

### 1. Rename and document execution modes

Outcome: the code and docs explain local versus cloud ownership clearly.

Changes:

- Use `cloud` as the public cloud run mode.
- Use `cloud` as the only public cloud run mode.
- Add a `make run-cloud` command and `scripts/run_cloud_pipeline.sh`.
- Keep `make run-local` as the default development command.
- Update README architecture and run instructions to show the two routes side by side.

Likely files:

- `Makefile`
- `scripts/run_cloud_pipeline.sh`
- `pipelines/flows/lending_pipeline_flow.py`
- `README.md`
- `docs/detailed/architecture.md`
- `docs/detailed/orchestration_runtime.md`

Verification:

```bash
make test
```

### 2. Add a raw artifact storage boundary

Outcome: extraction no longer assumes every raw artifact must first be a durable local file.

Changes:

- Add a small storage interface for raw artifacts, for example:
  - `LocalRawArtifactStore`
  - `S3RawArtifactStore`
- Local mode writes raw artifacts through the local store.
- Cloud mode writes raw artifacts through the S3 store.
- Preserve fixture mode and tests by letting fixtures use the local store.
- Keep `.tmp/` available for scratch/spooling only, not as the durable cloud source of truth.

Likely files:

- `pipelines/extract/`
- `pipelines/load/s3_loader.py`
- `pipelines/utils/paths.py`
- new module such as `pipelines/storage/raw_artifacts.py`
- tests under `tests/unit/`

Verification:

```bash
.venv/bin/python -m pytest tests/unit/test_paths.py tests/unit/test_s3_loader.py tests/unit/test_prefect_local_flow.py
```

### 3. Update manifests to describe storage explicitly

Outcome: manifests identify where the durable raw artifact lives, without treating `local_raw_path` as the universal source of truth.

Changes:

- Add canonical fields such as `raw_uri` and `storage_backend`.
- Continue recording `local_raw_path` when a local copy exists.
- Continue recording `s3_raw_uri` when an S3 object exists.
- Update raw validation and raw loaders to use the canonical durable URI for the selected route.
- Preserve existing manifest fields during transition if downstream models still depend on them.

Likely files:

- `pipelines/utils/manifest.py`
- `pipelines/validation/raw_checks.py`
- `pipelines/validation/schema_checks.py`
- `pipelines/load/raw_load_common.py`
- dbt staging models that read `raw_ingestion_manifest`

Verification:

```bash
.venv/bin/python -m pytest tests/unit/test_manifest.py tests/unit/test_raw_validation.py tests/integration/test_duckdb_loader.py
```

### 4. Make cloud extraction land raw artifacts directly in S3

Outcome: cloud mode does not need local raw storage for the durable raw data path.

Changes:

- For SBA downloads, stream source responses to S3 while computing checksum, size, and row count.
- For Census and BLS API JSON, write JSON payloads directly to S3 and compute manifest metadata from the payload.
- Write cloud manifests and validation output to S3.
- Use local scratch only when a parser or checksum step needs temporary buffering.
- Keep local extraction behavior unchanged for local mode.

Likely files:

- `pipelines/extract/sba_extract.py`
- `pipelines/extract/census_bds_extract.py`
- `pipelines/extract/bls_laus_extract.py`
- `pipelines/flows/lending_pipeline_flow.py`
- `pipelines/load/s3_loader.py`

Verification:

```bash
.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py tests/unit/test_s3_loader.py
```

### 5. Make raw validation storage-aware

Outcome: validation works for both local files and S3 objects through the same logical checks.

Changes:

- Keep the existing validation check IDs and semantics.
- Let validation read payloads through a storage resolver instead of directly calling `Path(...).read_text(...)`.
- In local mode, resolver reads local paths.
- In cloud mode, resolver reads S3 objects or object metadata.
- Missing S3 objects should produce blocking validation results, not unstructured boto errors.

Likely files:

- `pipelines/validation/raw_checks.py`
- `pipelines/validation/schema_checks.py`
- `pipelines/flows/lending_pipeline_flow.py`
- new storage resolver module if introduced

Verification:

```bash
.venv/bin/python -m pytest tests/unit/test_raw_validation.py tests/unit/test_prefect_local_flow.py
```

### 6. Load Snowflake raw tables from S3

Outcome: Snowflake raw loading becomes cloud-native.

Changes:

- Add Snowflake stage setup for the configured S3 raw landing zone.
- Add file-format definitions for CSV and JSON.
- Prefer `COPY INTO` from S3 stage into Snowflake raw tables.
- Use the S3-stage loader as the only Snowflake raw-load path.
- Record the raw load pattern in `raw_pipeline_run_summary`.
- Reconcile Snowflake row counts against manifests after load.

Likely files:

- `pipelines/load/snowflake_loader.py`
- `pipelines/flows/lending_pipeline_flow.py`
- tests under `tests/unit/test_snowflake_loader.py`

Verification:

```bash
.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py
```

### 7. Make dbt target ownership explicit

Outcome: dbt is clearly the same modeling layer running against either DuckDB or Snowflake.

Current handoff contract: dbt staging is shared across local and cloud routes.
Raw source rows and manifests must provide `raw_uri` and `storage_backend`;
staging joins raw rows to latest successful manifests by `pipeline_run_id`,
source resource, and `raw_uri`. dbt reads the raw source schema from
`RAW_SCHEMA`.

Changes:

- Document:
  - `dev_duckdb` builds local DuckDB models.
  - `prod_snowflake` builds Snowflake models.
- Ensure run summaries capture dbt target and route.
- Update dbt docs/readme language so Snowflake is the cloud warehouse, not a replacement for dbt.

Likely files:

- `dbt/profiles.yml` or profile template generation code
- `pipelines/flows/lending_pipeline_flow.py`
- `README.md`
- `docs/detailed/data_model.md`

Verification:

```bash
make dbt-local
```

Cloud verification remains credential-gated.

### 8. Clarify route-specific outputs

Outcome: the project tells a clean story about what each route produces.

Changes:

- Local route outputs:
  - DuckDB database file
  - local BI export CSVs
  - local run summary
  - local dbt artifacts
- Cloud route outputs:
  - S3 raw landing prefix
  - S3 manifests and validation output
  - Snowflake raw/staging/marts/BI/audit schemas
  - Snowflake BI tables for Power BI
  - uploaded dbt artifacts
- README should include a short "Which route should I run?" section.
- Add evidence checklist for recruiter screenshots:
  - local run command success
  - DuckDB table list or dbt local success
  - S3 raw prefix screenshot
  - Snowflake schema/table screenshot
  - dbt Snowflake build success
  - Power BI connected to BI tables

Likely files:

- `README.md`
- `docs/detailed/final_consolidation.md`
- `docs/detailed/orchestration_runtime.md`

Verification:

```bash
git diff --check
```

## Suggested Issue Sequence

1. [#40 Define local and cloud route terminology](https://github.com/stevennitesh/small-business-lending-pipeline/issues/40)
2. [#41 Add raw artifact storage boundary](https://github.com/stevennitesh/small-business-lending-pipeline/issues/41)
3. [#42 Make manifests route-aware for raw artifact storage](https://github.com/stevennitesh/small-business-lending-pipeline/issues/42)
4. [#43 Make cloud extraction land raw artifacts directly in S3](https://github.com/stevennitesh/small-business-lending-pipeline/issues/43)
5. [#44 Make raw validation storage-aware](https://github.com/stevennitesh/small-business-lending-pipeline/issues/44)
6. [#45 Load Snowflake raw tables from S3](https://github.com/stevennitesh/small-business-lending-pipeline/issues/45)
7. [#46 Clarify dbt route targets and output ownership](https://github.com/stevennitesh/small-business-lending-pipeline/issues/46)

This should be implemented sequentially. Each issue should leave the local route passing before moving to the next cloud enhancement.

## Acceptance Criteria

- `make run-local` remains the default local route and does not require AWS or Snowflake.
- The local route loads DuckDB, runs dbt with `dev_duckdb`, validates BI tables, and exports local Power BI CSVs.
- The cloud route writes durable raw artifacts directly to S3.
- The cloud route loads Snowflake raw tables from S3, not from local raw files.
- dbt runs against Snowflake with `prod_snowflake` and publishes Snowflake BI/audit outputs.
- README and architecture docs explain the two routes without implying that tools were added only for tool coverage.
- Tests cover local mode without cloud credentials and cloud logic through mocks/fakes where real credentials are not available.

## Final Verification Plan

Local verification:

```bash
make test
make run-local
make dbt-local
```

Cloud verification:

```bash
make run-cloud
```

Manual evidence:

- Confirm S3 raw objects exist under the expected partitioned prefix.
- Confirm Snowflake raw and BI schemas contain expected tables.
- Confirm Power BI can connect to the Snowflake BI schema or the local export route.

## Open Questions

- Should validation read full large S3 objects for row counts, or should extraction compute and trust manifest row counts while validation checks object existence, checksum, schema metadata, and source identity?
