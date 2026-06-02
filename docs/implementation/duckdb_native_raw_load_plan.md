# Plan: Lower Local DuckDB Raw Load Memory Cost

## Goal

Reduce the local raw-load memory spike by loading large SBA CSV extracts into
DuckDB with DuckDB-native CSV scans instead of building full pandas frames in
Python first.

This is a local-route optimization. The cloud route should stay cloud-native:
Snowflake continues to load S3-backed artifacts through stages and `COPY INTO`.

## Problem

The local live raw-load benchmark showed that loading existing raw files into
DuckDB completed successfully, but used much more memory than the final local
warehouse size justifies:

- Command: load existing live raw manifests for
  `live-postmerge-pipeline-check-20260520` into local DuckDB.
- Observed wall time: about `28.6` seconds.
- Observed max RSS: about `4.7 GB`.
- Observed DuckDB size after raw load: about `186 MB`.
- Loaded source row counts:
  - `raw.raw_sba_7a_foia`: `1,947,098`.
  - `raw.raw_sba_504_foia`: `227,404`.
  - `raw.raw_bls_laus_state_month`: `22,746`.
  - `raw.raw_census_bds_state_year`: `1,734`.

The bottleneck is not the cloud route and not final warehouse disk size. At the
time this plan was written, it was the local Python handoff for large CSVs:

- a shared local-source helper read SBA CSVs with `pd.read_csv(...)`;
- `load_local_source_frame(...)` enriched each frame with metadata.
- `pd.concat(frames, ignore_index=True)` copies all source partitions into one
  large frame.
- `pipelines/load/duckdb_loader.py` registers that full frame and creates the
  raw DuckDB table from it.

That shape is simple, but it is memory-heavy for WSL because the CSV data,
metadata-enriched copies, concatenated frame, and DuckDB ingestion can overlap
in memory.

## Non-goals

- Do not change extraction, raw validation, dbt model logic, BI exports, or
  Power BI report visuals.
- Do not change the Snowflake S3-stage raw load path.
- Do not remove raw artifact manifests, checksums, row-count reconciliation, or
  validation gating.
- Do not optimize Census or BLS JSON loading in this slice; those files are
  small enough that pandas is not the current risk.
- Do not delete local raw data or change retention policy.
- Do not make `make run-local-live` cheaper by silently skipping required work.

## Constraints

- Keep the local route and cloud route explicit:
  - Local route: local raw files to DuckDB.
  - Cloud route: S3 artifacts to Snowflake.
- Preserve the raw source table names and metadata columns consumed by dbt.
- Preserve row-count checks against manifest `row_count`.
- Keep generated benchmark output under `.tmp/benchmarks/`.
- Preserve the user-owned `powerbi/lending_dashboard.pbix` change.
- Avoid WSL-crashing verification commands; benchmark against existing raw
  files before considering any live re-download.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. The loader change touches one hot path and should land with its tests
  before live benchmarking.

## Acceptance Checks

- Local DuckDB SBA raw tables load from `local_raw_path` through DuckDB-native
  CSV scans, not pandas source frames.
- Census and BLS JSON source tables continue to load through the existing small
  normalized-frame path.
- Raw source tables still include the existing metadata columns:
  `pipeline_run_id`, `source_system`, `source_dataset`,
  `source_resource_name`, `ingestion_date`, `storage_backend`, `raw_uri`,
  `raw_file_path`, `s3_raw_uri`, and `sha256_checksum`.
- Local raw load still fails on failed raw-validation results.
- Local raw load still fails on empty required manifest groups.
- Local raw load still reconciles row counts against manifests.
- Snowflake raw load tests continue to pass without route changes.
- A live raw-load benchmark against existing raw artifacts shows materially
  lower peak memory than the `~4.7 GB` baseline, while preserving row counts.

## Baseline

- Working tree currently has unrelated or already-in-progress changes in:
  - `scripts/benchmark_local_command.py`.
  - `tests/unit/test_benchmark_local_command.py`.
  - `dbt/dbt_project.yml`.
  - `powerbi/lending_dashboard.pbix` (user-owned, do not touch).
- Current local raw-load entry point:
  - `pipelines/load/duckdb_loader.py::load_raw_extracts`.
- Current small-source local helper:
  - `pipelines/load/raw_load_local_sources.py::load_local_source_frame`.
- Current cloud raw-load entry point:
  - `pipelines/load/snowflake_loader.py::load_raw_extracts_to_snowflake_from_s3`.
- Current focused tests:
  - `tests/integration/test_duckdb_loader.py`.
  - `tests/unit/test_snowflake_loader.py`.
- Benchmark evidence already collected:
  - Existing live raw-load benchmark: max RSS about `4.7 GB`.
  - After dbt materialization tuning, dbt full validation is no longer the main
    runtime bottleneck; local raw load remains the main local-route memory risk.

## Proposed Design

Add a DuckDB-local loading branch for large CSV-backed source tables:

- Keep manifest and validation-result loading in shared helpers.
- Keep source routing in `duckdb_loader.py` so local behavior is obvious.
- For `raw.raw_sba_7a_foia` and `raw.raw_sba_504_foia`:
  - create or replace the target table from the first manifest's CSV using
    DuckDB `read_csv` / `read_csv_auto`;
  - insert each later manifest with the same SQL shape;
  - add manifest metadata as SQL literal columns during the scan;
  - set CSV columns to string-friendly types where needed so downstream dbt
    casts remain responsible for trusted types.
- For `raw.raw_census_bds_state_year` and `raw.raw_bls_laus_state_month`:
  - keep the existing pandas normalized-frame helper for now.
- Keep metadata/audit tables on the existing normalized-record helper because
  they are small.

This gives each route a deliberate role:

- DuckDB local route uses DuckDB to scan local CSVs directly.
- Snowflake cloud route uses Snowflake to scan staged S3 files directly.
- Shared helpers remain for route-neutral manifest, validation, and metadata
  contracts.

## Tasks

### Task 1: Protect Existing Local Raw Load Contracts

- Outcome: Add or adjust tests that describe the local raw-load contract before
  changing the implementation.
- Builds on or must preserve: existing DuckDB loader row-count, metadata,
  validation-failure, and empty-manifest behavior.
- Existing logic to reuse or extend:
  - `tests/integration/test_duckdb_loader.py`.
  - `pipelines/load/duckdb_loader.py::load_raw_extracts`.
- Public contract or state/data change: none.
- Depends on: none.
- Likely files/modules:
  - `tests/integration/test_duckdb_loader.py`.
- First command/check:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py`.
- Change boundary:
  - Tests only. Do not change loader behavior yet.
- Verification command:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py`.
- Review focus:
  - Tests should assert metadata and row-count behavior, not implementation
    details that make the native loader harder to add.
- Risk/rollback:
  - If existing tests already cover a contract well, avoid duplicate tests.
- Stop/ask if:
  - The desired local raw table schema conflicts with current dbt source usage.
- Status: pending.

### Task 2: Add DuckDB-Native SBA CSV Loading

- Outcome: Load large SBA CSV manifest groups directly through DuckDB SQL rather
  than `pd.read_csv` plus `pd.concat`.
- Builds on or must preserve: Task 1 contract tests and existing manifest
  validation gates.
- Existing logic to reuse or extend:
  - `pipelines/load/duckdb_loader.py::load_raw_extracts`.
  - `pipelines/load/duckdb_loader.py::LOCAL_DUCKDB_NATIVE_CSV_TABLES`.
  - `pipelines/load/raw_load_local_sources.py::LOCAL_FRAME_SOURCE_TABLE_KINDS`.
  - existing row-count reconciliation in `duckdb_loader.py`.
- Public contract or state/data change:
  - Raw table content should be equivalent, but physical loading is more
    memory-efficient.
- Depends on: Task 1.
- Likely files/modules:
  - `pipelines/load/duckdb_loader.py`.
  - `pipelines/load/raw_load_local_sources.py`.
  - `pipelines/load/raw_load_metadata.py`.
  - `tests/integration/test_duckdb_loader.py`.
- First command/check:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py`.
- Change boundary:
  - Only local DuckDB SBA CSV loading. Do not change Snowflake, extraction, dbt,
    or BI exports.
- Verification command:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py`.
- Review focus:
  - SQL should quote identifiers and metadata values safely.
  - The first-manifest create path and later-manifest insert path should produce
    the same schema.
  - Loading should not require all SBA CSVs to exist in memory at once.
- Risk/rollback:
  - DuckDB CSV inference could differ from pandas. Mitigate by using
    string-friendly/raw-preserving options and by checking downstream dbt.
- Stop/ask if:
  - DuckDB cannot preserve required raw column names from the SBA CSVs without a
    broader source schema contract.
- Status: pending.

### Task 3: Make The Local/Cloud Route Boundary Obvious In Loader Code

- Outcome: Keep route-specific code readable so future maintainers do not
  reintroduce local pandas loading for cloud or S3-stage assumptions for local.
- Builds on or must preserve: Task 2 native local SBA path and existing
  Snowflake S3 path.
- Existing logic to reuse or extend:
  - local `duckdb_loader.py` routing.
  - cloud `snowflake_loader.py` S3 manifest checks.
  - shared `raw_load_inputs.py` manifest/validation helpers.
  - shared `raw_load_metadata.py` metadata helpers.
- Public contract or state/data change: none.
- Depends on: Task 2.
- Likely files/modules:
  - `pipelines/load/duckdb_loader.py`.
  - `pipelines/load/raw_load_inputs.py`.
  - `pipelines/load/raw_load_metadata.py`.
- First command/check:
  - `rg -n "load_local_source_frame|read_csv|COPY INTO|s3_stage" pipelines/load`.
- Change boundary:
  - Small naming/comments/refactor only where it clarifies the route boundary.
- Verification command:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py tests/unit/test_snowflake_loader.py`.
- Review focus:
  - Shared helpers should stay route-neutral.
  - Local route should say "local DuckDB native scan"; cloud route should say
    "S3 stage copy".
- Risk/rollback:
  - Avoid moving too much shared code in the same slice; clarity should not
    become a broad refactor.
- Stop/ask if:
  - The cleanup would require changing public loader function names or flow
    arguments.
- Status: pending.

### Task 4: Benchmark Existing Live Raw Artifacts After The Loader Change

- Outcome: Produce new raw-load benchmark evidence without re-downloading live
  source data.
- Builds on or must preserve: Task 2 row-count behavior.
- Existing logic to reuse or extend:
  - `scripts/benchmark_local_command.py`.
  - existing raw manifests for
    `live-postmerge-pipeline-check-20260520`, if still present.
- Public contract or state/data change:
  - Writes benchmark output under `.tmp/benchmarks/`.
  - May overwrite the local DuckDB warehouse during benchmark verification.
- Depends on: Tasks 2 and 3.
- Likely files/modules:
  - `.tmp/` benchmark helper, or a tiny durable benchmark helper if needed.
  - `data/warehouse/small_business_lending.duckdb` as generated output only.
- First command/check:
  - Verify existing raw manifests and raw files are present before running the
    benchmark.
- Change boundary:
  - No source changes unless the benchmark exposes a correctness bug.
- Verification command:
  - `make benchmark-local COMMAND=".venv/bin/python .tmp/load_existing_live_raw_duckdb.py --pipeline-run-id live-postmerge-pipeline-check-20260520"`.
- Review focus:
  - Compare max RSS, wall time, DuckDB size delta, and all raw row counts to the
    baseline.
- Risk/rollback:
  - If the old scratch helper is gone, recreate it under `.tmp/` or add a
    narrow durable helper only if repeated benchmarking justifies it.
- Stop/ask if:
  - Existing raw files are missing and re-downloading live data would be needed.
- Status: pending.

### Task 5: Verify Downstream Local BI Still Works

- Outcome: Prove the optimized local raw load still produces usable modeled BI
  outputs.
- Builds on or must preserve: Tasks 2 and 4 raw table equivalence.
- Existing logic to reuse or extend:
  - `make dbt-build-local-fast`.
  - `make powerbi-refresh-local`.
  - `make powerbi-model-check`.
- Public contract or state/data change:
  - Regenerates local dbt tables and Power BI CSV artifacts from the current
    local DuckDB warehouse.
- Depends on: Task 4.
- Likely files/modules:
  - generated data under `data/warehouse` and `data/exports/powerbi`.
- First command/check:
  - `make dbt-build-local-fast`.
- Change boundary:
  - Verification only unless a downstream incompatibility is found.
- Verification command:
  - `make dbt-build-local-fast`.
  - `make powerbi-refresh-local`.
  - `make powerbi-model-check`.
  - `git diff --check`.
- Review focus:
  - BI row counts and contract should remain consistent with the current live
    local warehouse; generated CSVs should remain uncommitted unless explicitly
    requested.
- Risk/rollback:
  - If BI output changes unexpectedly, compare raw table schemas and row counts
    first before changing marts or export code.
- Stop/ask if:
  - Full live extraction is needed to explain a discrepancy.
- Status: pending.

## Final Verification

Required:

- `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py`.
- `.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py`.
- `make benchmark-local COMMAND=".venv/bin/python .tmp/load_existing_live_raw_duckdb.py --pipeline-run-id live-postmerge-pipeline-check-20260520"`.
- `make dbt-build-local-fast`.
- `make powerbi-refresh-local`.
- `make powerbi-model-check`.
- `git diff --check`.

Optional when WSL has enough memory headroom:

- `make dbt-build-local-full`.
- `make benchmark-local COMMAND="make dbt-build-local-full"`.

## Expected Result

The local raw load should still produce the same raw table row counts and
metadata, but with lower peak RSS because SBA CSV data no longer has to be held
as a full pandas-concatenated frame before DuckDB writes it.

The project should keep a clean professional split:

- Local development and BI prototyping use local raw files and DuckDB.
- Cloud promotion uses S3-backed manifests and Snowflake stages.
- dbt remains the shared transformation contract on top of either warehouse.

## Benchmark Evidence

Native DuckDB CSV loading was benchmarked against existing raw artifacts for
`live-postmerge-pipeline-check-20260520` without re-downloading source data.

- Benchmark output:
  `.tmp/benchmarks/20260524T012337Z-home-steve-code-small-business-lending-pipeline-venv-bin-python-tmp-load-existin.json`.
- Wall time: `18.069` seconds, improved from the prior `28.6` second baseline.
- Max RSS: `2,002,464,768` bytes, improved from the prior `~4.7 GB` baseline.
- DuckDB size: `182,202,368` bytes.
- Row counts matched the baseline:
  - `raw.raw_sba_7a_foia`: `1,947,098`.
  - `raw.raw_sba_504_foia`: `227,404`.
  - `raw.raw_bls_laus_state_month`: `22,746`.
  - `raw.raw_census_bds_state_year`: `1,734`.
  - `raw.raw_ingestion_manifest`: `8`.
  - `raw.raw_validation_result`: `92`.
  - `raw.raw_pipeline_run_summary`: `1`.

## Downstream Verification Evidence

The native-loaded local DuckDB warehouse was used to rebuild dbt models and
Power BI CSV exports.

- `make dbt-build-local-fast` passed with 4 seeds, 51 models, and 33 critical
  tests.
- `make powerbi-refresh-local` passed and exported 17 BI CSV tables.
- Exported Power BI row counts included:
  - `bi_executive_overview`: `1,887`.
  - `bi_lender_mix`: `149,873`.
  - `bi_industry_mix`: `31,733`.
  - `bi_regional_business_health`: `1,734`.
  - `bi_year_filter`: `37`.
- `make powerbi-model-check` passed with 17 tables, 25 relationships, and
  filter coverage for industry, lender, program, region, state, and year.
- `git diff --check` passed.

## Open Questions

- Should the native DuckDB loader force every raw CSV column to text for maximum
  raw fidelity, or preserve DuckDB's inferred types where safe? The safer MVP
  default is raw text plus downstream dbt casts.
- Should repeated live raw-load benchmarking get a durable script instead of a
  `.tmp/` helper? Start with `.tmp`; promote only if this becomes a regular
  workflow.
- Should Census/BLS JSON loading eventually move to DuckDB-native JSON scans?
  Not in this slice, because current file sizes do not justify the extra
  complexity.
