# Plan: Align Power BI Handoff Contract

## Goal

Make the dbt mart to Power BI handoff fully deliberate for both supported routes:

- local route: dbt builds DuckDB BI tables, then exports Power BI-ready CSVs from the same contract Power BI reads;
- cloud route: dbt builds Snowflake BI tables, and Power BI can connect directly to the same logical BI contract in Snowflake;
- Power BI owns relationships, slicers, display formatting, and lightweight labels only;
- dbt owns dashboard facts, dimensions/filter tables, KPI values, known-lender semantics, and data-quality/status fields.

## Non-goals

- Do not edit `powerbi/lending_dashboard.pbix`.
- Do not move core KPI calculations into Power BI.
- Do not add new dashboard pages or visual design changes.
- Do not change raw, staging, mart fact, or mart context business logic unless needed to expose a BI-facing table.
- Do not add DirectQuery or Power BI service deployment automation in this slice.

## Constraints

- Keep local and cloud report surfaces semantically equivalent.
- Keep local CSVs under `data/exports/powerbi/` so Power Query can load stable paths.
- Keep Snowflake Power BI sources out of raw and staging schemas.
- Prefer BI-schema/filter-table outputs for Power BI instead of having Power BI consume internal mart dimensions directly.
- Keep rates and shares as decimal values; Power BI handles formatting.
- Preserve the existing user-owned `powerbi/lending_dashboard.pbix` modification; do not stage or modify it.

## Execution Mode

Execution mode: sequential.

The tasks touch overlapping BI contracts, export code, model JSON, Power Query, and tests, so implement one issue/slice at a time in a single workspace.

## Baseline

- Working tree: clean except user-owned `powerbi/lending_dashboard.pbix`.
- Current local path:
  - dbt builds DuckDB tables.
  - `scripts/export_powerbi_tables.py` exports 12 tables to stable `data/exports/powerbi/*.csv`.
  - The Prefect local flow exports only the 9 `bi_*` tables and writes them under run-specific folders.
  - `powerbi/power_query/local_csv_queries.pq` loads only the 9 `bi_*` tables.
- Current cloud path:
  - dbt builds Snowflake tables using schema generation rules.
  - The model JSON points all Power BI Snowflake sources at one `${SNOWFLAKE_SCHEMA}` even though internal dimensions currently live under mart schema rules.
- Current tests:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_dbt_bi_pipeline_models.py` passes.
  - `make powerbi-model-check` passes.

## Acceptance Checks

- dbt exposes all Power BI relationship/filter tables as BI-facing models, including a year filter table.
- Power BI no longer needs to create relationship dimensions manually except for relationships themselves.
- Local CSV exports and cloud Snowflake tables use the same logical table list.
- Prefect local flow and standalone export script use one shared Power BI export contract.
- Power Query loads every local CSV table required by the model contract.
- Power BI model JSON points Snowflake sources at BI-facing tables only, not raw, staging, or internal marts dimensions.
- Tests fail if BI model JSON, Power Query, export contract, and flow BI validation table list drift.
- Existing PBIX remains untouched.

## GitHub Issues

- [#75 Add BI-facing filter tables for Power BI](https://github.com/stevennitesh/small-business-lending-pipeline/issues/75)
- [#76 Use one shared Power BI export contract in local flow](https://github.com/stevennitesh/small-business-lending-pipeline/issues/76)
- [#77 Update Power BI model and Power Query contract](https://github.com/stevennitesh/small-business-lending-pipeline/issues/77)
- [#78 Add Power BI handoff drift tests](https://github.com/stevennitesh/small-business-lending-pipeline/issues/78)

## Tasks

### Task 1: Add BI-facing filter tables in dbt

- Outcome: Power BI relationship/filter tables are produced by dbt in the BI surface.
- Builds on or must preserve: existing `bi_state_filter`, mart dimensions, and BI fact/output tables.
- Existing logic to reuse or extend:
  - `bi_state_filter` as the state/region pattern.
  - `dim_loan_program`, `dim_naics`, and `dim_lender` as source dimensions.
  - year fields from BI tables.
- Public contract or state/data change:
  - Add `bi_year_filter`.
  - Add BI-facing program, industry, and lender filter tables, likely `bi_loan_program_filter`, `bi_naics_filter`, and `bi_lender_filter`.
  - Keep unknown flags where useful, but BI lender filter should still support known-lender visuals cleanly.
- Depends on: none.
- Likely files/modules:
  - `dbt/models/bi/bi_year_filter.sql`
  - `dbt/models/bi/bi_loan_program_filter.sql`
  - `dbt/models/bi/bi_naics_filter.sql`
  - `dbt/models/bi/bi_lender_filter.sql`
  - `dbt/models/bi/schema.yml`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_bi_pipeline_models.py`
- Change boundary:
  - Do not change existing KPI models except where required to derive `bi_year_filter`.
  - Do not remove internal mart dimensions; they remain dbt modeling inputs.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_bi_pipeline_models.py`
  - `make dbt-local`
- Review focus:
  - Filter tables are BI-facing and route-neutral.
  - Year table covers both `year` and `approval_year` BI outputs.
- Risk/rollback:
  - Low; additive dbt models. Roll back by removing new BI filter models and reverting contract updates.
- Status: completed in #75

### Task 2: Make local export use one shared Power BI contract

- Outcome: local pipeline and standalone export script export the same Power BI table set to stable CSV paths.
- Builds on or must preserve: Task 1 BI-facing table list.
- Existing logic to reuse or extend:
  - `scripts/export_powerbi_tables.py` table list, required columns, row-count checks, and prohibited-field checks.
  - `validate_bi_tables` and `export_bi_tables` flow tasks.
- Public contract or state/data change:
  - Replace internal flow-only `BI_TABLES` drift with the shared export contract.
  - Local Power BI CSVs are written to `data/exports/powerbi/*.csv`, matching Power Query.
  - Run summary can still record exported paths, but Power BI should read the stable latest output location.
- Depends on: Task 1.
- Likely files/modules:
  - `scripts/export_powerbi_tables.py`
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_powerbi_export.py`
  - `tests/unit/test_prefect_local_flow.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_prefect_local_flow.py`
- Change boundary:
  - Do not export raw, staging, or internal fact tables.
  - Do not add Snowflake CSV export; cloud report path is direct Snowflake BI tables.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - The flow and script cannot disagree about exported Power BI tables.
  - The flat path expected by Power Query is produced by local route.
- Risk/rollback:
  - Medium: local run summary export path behavior changes from run-specific to stable latest CSVs. Roll back by restoring run-specific export while keeping shared table list.
- Status: completed in #76

### Task 3: Update Power BI model and Power Query contract

- Outcome: the source-controlled Power BI contract matches the dbt-produced BI surface for both local CSV and Snowflake.
- Builds on or must preserve: Tasks 1-2 table names and stable CSV paths.
- Existing logic to reuse or extend:
  - `powerbi/lending_dashboard_model.json` table, relationship, measure, and source-mode structure.
  - `powerbi/power_query/local_csv_queries.pq` local CSV loader.
  - `scripts/validate_powerbi_model.py` validation rules.
- Public contract or state/data change:
  - Model JSON uses BI-facing filter table names instead of internal `dim_*` table names.
  - Snowflake table references point to BI schema tables for every Power BI source.
  - Power Query loads every local CSV required by the model contract.
  - Relationships remain one-to-many and single-direction.
- Depends on: Tasks 1-2.
- Likely files/modules:
  - `powerbi/lending_dashboard_model.json`
  - `powerbi/power_query/local_csv_queries.pq`
  - `powerbi/README.md`
  - `scripts/validate_powerbi_model.py`
  - `tests/unit/test_powerbi_model_contract.py`
- First command/check:
  - `make powerbi-model-check`
- Change boundary:
  - Do not edit the PBIX.
  - Do not add report-only calculations as required semantic model fields.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
  - `make powerbi-model-check`
- Review focus:
  - Local and cloud source modes name the same logical tables.
  - Contract does not point to raw/staging/internal marts tables.
- Risk/rollback:
  - Medium: manual Power BI relationship setup instructions change. Roll back by restoring old model JSON and Power Query entries.
- Status: completed in #77

### Task 4: Add cross-contract drift tests

- Outcome: future changes cannot silently break the dbt BI/export/Power BI handoff.
- Builds on or must preserve: Tasks 1-3 final table names.
- Existing logic to reuse or extend:
  - `tests/unit/test_powerbi_export.py`
  - `tests/unit/test_powerbi_model_contract.py`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
  - `tests/unit/test_prefect_local_flow.py`
- Public contract or state/data change:
  - Tests assert that dbt BI schema, export contract, Power Query, model JSON, and flow validation/export table lists agree.
  - Tests assert prohibited fields stay out of the Power BI surface.
- Depends on: Tasks 1-3.
- Likely files/modules:
  - `tests/unit/test_powerbi_export.py`
  - `tests/unit/test_powerbi_model_contract.py`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
  - `tests/unit/test_prefect_local_flow.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_prefect_local_flow.py`
- Change boundary:
  - Do not require a live PBIX or Power BI Desktop.
  - Do not require live Snowflake for unit tests.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - Tests validate contracts, not implementation trivia.
  - Tests remain fast and WSL-safe.
- Risk/rollback:
  - Low; test-only hardening around the new contract.
- Status: completed in #78

## Final Verification

Run focused checks:

```bash
.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_prefect_local_flow.py
make powerbi-model-check
make dbt-local
git diff --check
```

Optional when WSL has enough memory and the current local warehouse is available:

```bash
make run-local
```

Cloud-route verification should use the existing configured Snowflake account:

```bash
make run-cloud
```

For cloud verification, passing means dbt builds Snowflake BI tables and `validate_bi_tables` confirms non-empty BI-facing tables. It does not require opening Power BI Desktop.

## Open Questions

- Should local route keep run-specific CSV snapshots in addition to stable latest CSVs?
  - Recommendation: not for MVP. Keep stable latest CSVs for Power BI and use run summary/dbt artifacts for run history.
- Should unknown lenders appear in `bi_lender_filter`?
  - Recommendation: exclude or clearly flag unknown lenders from lender slicers because lender-specific marts are known-lender only. Preserve `UNKNOWN` internally in `dim_lender`.
- Should Power BI cloud mode connect to tables named `BI_*` only?
  - Recommendation: yes. Expose all dashboard facts and filters from the dbt BI schema so report authors do not need to know internal mart schemas.
