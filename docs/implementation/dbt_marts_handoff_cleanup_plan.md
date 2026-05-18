# Plan: Clean Up dbt Marts Handoff Contract

## Summary

Tighten the handoff from dbt staging into dbt marts so marts consume staged contracts consistently, preserve local/cloud lineage deliberately, and mark stale compatibility surfaces before removing them.

This is a cleanup pass, not a KPI redesign. The intended shape is:

- raw load owns raw tables;
- dbt staging owns normalized typed source contracts;
- dbt marts own reusable facts, dimensions, audit marts, and business calculations;
- BI models consume marts, not raw or staging implementation details.

## Current Findings

The marts layer is mostly aligned with the local/cloud route split:

- Fact models consume staging models such as `stg_sba_loans`, `stg_bds_state_year`, and `stg_laus_state_month`.
- Facts preserve route-neutral lineage fields such as `pipeline_run_id`, `storage_backend`, `raw_uri`, `raw_file_path`, and `sha256_checksum`.
- Facts join to `dim_source_file` through `raw_uri`, so local and cloud runs can share the same mart logic.
- Context and lending marts consume facts and dimensions rather than raw extracts.
- SQL dialect branches using `target.type` are intentional DuckDB/Snowflake syntax compatibility, not old local/cloud route compatibility.

The main cleanup issues are narrow:

- `dbt/models/marts/pipeline/mart_pipeline_run_summary.sql` still reads `source('raw', 'raw_pipeline_run_summary')` directly, bypassing staging.
- `dbt/models/marts/schema.yml` describes `dim_source_file.source_file_key` as a key for a "raw file and checksum pair", but the model generates it from `raw_uri` only.
- Some lineage fields still carry local/cloud vocabulary because they are useful for observability, but they should be treated as deliberate lineage metadata rather than route-specific mart logic.

## Goals

- Add a staged contract for pipeline run summary metadata.
- Route pipeline marts through staging refs instead of raw sources.
- Make `dim_source_file` documentation and tests match the actual identity contract.
- Keep useful local/cloud lineage fields where they support traceability.
- Tag stale compatibility candidates so removal can be deliberate.

## Non-Goals

- Do not change KPI formulas or business mart grain.
- Do not split marts into separate local and cloud model trees.
- Do not remove Power BI-facing compatibility fields in this pass.
- Do not change extraction, raw validation, raw load, or orchestration behavior.
- Do not run heavy full live-data dbt builds unless explicitly needed.

## Recommended Changes

### 1. Add Staged Pipeline Run Summary

Create `dbt/models/staging/audit/stg_pipeline_run_summary.sql` over `source('raw', 'raw_pipeline_run_summary')`.

Preserve the current pipeline summary contract, including:

- `pipeline_run_ids`
- `loaded_at_utc`
- `raw_table_count`
- `validation_status`

Add schema documentation and basic tests in `dbt/models/staging/schema.yml`.

Update staging unit tests so this model is part of the expected staging model set.

### 2. Route Pipeline Mart Through Staging

Update `dbt/models/marts/pipeline/mart_pipeline_run_summary.sql` to consume `ref('stg_pipeline_run_summary')`.

Add or update a static model test to assert marts do not read raw sources directly for this pipeline summary path.

### 3. Tighten Source File Dimension Contract

Update `dbt/models/marts/schema.yml` for `dim_source_file` so:

- `source_file_key` is documented as a surrogate key generated from `raw_uri`;
- `raw_uri` is documented as the route-neutral source artifact identity;
- `storage_backend` is documented as local/cloud lineage metadata;
- `raw_file_path` and `s3_raw_uri` are documented as optional route-specific lineage fields.

Add static tests that protect the current join contract:

- `dim_source_file` generates `source_file_key` from `raw_uri`;
- fact models join to `dim_source_file` by `raw_uri`;
- fact models expose `source_file_key` after the join.

### 4. Tag Stale And Compatibility Candidates

Use the following triage labels during implementation:

| Status | Location | Finding | Recommended Action |
| --- | --- | --- | --- |
| `stale-now` | `dbt/models/marts/pipeline/mart_pipeline_run_summary.sql` | Mart reads raw source directly. | Replace with staging ref in this cleanup. |
| `stale-now` | `dbt/models/marts/schema.yml` | `source_file_key` docs mention checksum-pair identity, but code uses `raw_uri`. | Correct docs/tests in this cleanup. |
| `keep-for-now` | `dim_source_file`, fact models | `raw_file_path`, `s3_raw_uri`, `storage_backend` lineage fields. | Keep as deliberate observability fields until BI/export review. |
| `out-of-scope` | `dbt/models/bi/schema.yml` | Deprecated BI compatibility fields for existing Power BI queries. | Review during BI subsystem cleanup. |
| `out-of-scope` | `pipelines/flows/lending_pipeline_flow.py` | Local-to-S3 testing/compatibility hooks. | Review during orchestration cleanup if still needed. |
| `intentional` | dbt models/macros using `target.type` | DuckDB/Snowflake SQL dialect differences. | Keep; this is not stale route compatibility. |

## Acceptance Criteria

- Pipeline run summary has a staging model with docs/tests.
- Pipeline run summary mart consumes the staging model, not the raw source.
- `dim_source_file` docs match the actual `raw_uri`-based identity contract.
- Static tests cover the marts-to-source-file join contract.
- Stale compatibility candidates are either removed in-scope or tagged for a later subsystem review.
- Local and cloud paths continue to share the same marts logic, with route differences expressed only through lineage metadata and adapter-specific SQL dialect.

## Verification Plan

Run focused checks first:

```bash
.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_bi_pipeline_models.py
.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_context_marts.py
```

Then run the lightweight dbt compile/build check:

```bash
make dbt-local
```

Finish with:

```bash
git diff --check
```

## Open Decisions

- `raw_file_path` should probably stay through the BI cleanup pass because it is useful local lineage and is currently blocked from BI exports where inappropriate.
- Deprecated BI compatibility fields should be reviewed when we analyze the BI subsystem, not during marts cleanup.
- Orchestration testing hooks should be reviewed during orchestration cleanup, after dbt marts and BI contracts are stable.
