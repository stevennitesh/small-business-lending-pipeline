# Plan: Clean Up `fact_sba_loans` Cost And Safety

## Goal

Make the next dbt optimization slice understandable, low-risk, and benchmark
driven after the materialization policy change. The focus is `fact_sba_loans`,
because the latest full local benchmark identified it as the slowest dbt node.

## Non-goals

- Do not change KPI definitions, Power BI table contracts, source contracts, or
  local/cloud route boundaries.
- Do not introduce incremental models, Snowflake clustering, partitioning, or
  environment-specific materialization in this slice.
- Do not make staging tables by default unless the benchmark after the lighter
  cleanup still justifies a separate experiment.

## Constraints

- Preserve the same modeled columns and row grain: one row per SBA loan record.
- Preserve referential integrity through existing dbt relationship tests.
- Keep the same SQL logic portable across local DuckDB and cloud Snowflake dbt
  targets.
- Leave `powerbi/lending_dashboard.pbix` and generated benchmark/export/dbt
  artifacts uncommitted.

## Baseline

- Current slow node: `model.small_business_lending_pipeline.fact_sba_loans`.
- Current source path: `fact_sba_loans` reads the `stg_sba_loans` view, which
  unions `stg_sba_7a_loans` and `stg_sba_504_loans`.
- Current cost pattern:
  - `fact_sba_loans` joins `dim_lender` on cleaned lender name to retrieve
    `lender_key`.
  - `fact_sba_loans` joins `dim_source_file` on `raw_uri` to retrieve
    `source_file_key`.
  - `stg_sba_loans` uses `select *` on both SBA staging branches before
    `union all`.

## Implementation Evidence

### Task 1 Result

- Commit `dc82bf3` generates `lender_key` and `source_file_key` directly in
  `fact_sba_loans` from the same deterministic inputs used by `dim_lender` and
  `dim_source_file`.
- Pre-change and post-change fact shape matched:
  - row count: `2,174,502`;
  - `lender_key` nulls: `0`;
  - `source_file_key` nulls: `0`;
  - `UNKNOWN` lender rows: `109,190`.
- `scripts/run_dbt_local.sh build --select fact_sba_loans+` passed and the
  existing relationship tests continued to validate referential integrity.

### Task 2 Result

- Commit `ec9715c` replaces `select *` in `stg_sba_loans` with the explicit SBA
  standardized column list for both 7(a) and 504 branches.
- `tests/unit/test_dbt_staging_models.py` now rejects `select *` in the SBA
  union and verifies both branches use the same ordered column contract.
- `scripts/run_dbt_local.sh build --select stg_sba_loans+` passed with
  `PASS=203 WARN=0 ERROR=0 SKIP=0`.

### Task 3 Benchmark Result

Benchmarks were refreshed on 2026-05-24 after Tasks 1 and 2:

- `make benchmark-local COMMAND="make dbt-build-local-full"` passed with
  `28.382s` wall time, `7,713,222,656` bytes max RSS, DuckDB size
  `615,002,112` bytes, and `0` byte `data/raw` delta.
- Slowest full-build dbt node remained
  `model.small_business_lending_pipeline.fact_sba_loans`, now at about
  `11.86s`.
- `make benchmark-local COMMAND="make powerbi-refresh-local"` passed with
  `26.113s` wall time, `7,454,937,088` bytes max RSS, DuckDB size
  `654,061,568` bytes, and `0` byte `data/raw` delta.
- Power BI export row counts stayed in the expected live-data shape, including
  `bi_executive_overview=1,887`, `bi_lender_mix=149,873`,
  `bi_industry_mix=31,733`, `bi_regional_business_health=1,734`, and
  `bi_year_filter=37`.
- `make powerbi-model-check` passed with 17 tables, 25 relationships, and
  filter coverage for industry, lender, program, region, state, and year.

Decision: defer an `int_sba_loans_standardized` table experiment. The fact
model is still the slowest single node, but the full local build is comfortably
under one minute and slightly faster than the prior materialization benchmark.
Adding another persisted intermediate table is not justified in this slice.

## Tasks

### Task 1: Replace Deterministic Key Lookups In `fact_sba_loans`

- Outcome: Generate deterministic `lender_key` and `source_file_key` directly
  in `fact_sba_loans` instead of joining dimensions only to retrieve those keys.
- Builds on or must preserve: `dim_lender` and `dim_source_file` key generation
  macros and existing relationship tests.
- Existing logic to reuse or extend:
  - `dim_lender` uses `generate_surrogate_key(["lender_name"])`.
  - `dim_source_file` uses `generate_surrogate_key(["raw_uri"])`.
- Public contract or state/data change: no output column names, grain, or KPI
  semantics should change.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_sba_loans.sql`
  - `dbt/models/marts/schema.yml` only if test descriptions need clarification.
- First command/check:
  - Capture current row count and key null counts from `fact_sba_loans`.
- Verification command:
  - `scripts/run_dbt_local.sh build --select fact_sba_loans+`
  - `make dbt-build-local-fast`
- Review focus:
  - Ensure generated keys exactly match dimension key logic.
  - Ensure unknown lender behavior is preserved.
  - Ensure relationship tests still prove keys exist in dimensions.
- Risk/rollback:
  - Risk is broken key parity; rollback is restoring dimension joins.
- Stop/ask if:
  - Generated key logic differs between fact and dimensions, or `UNKNOWN`
    handling cannot be preserved without a join.

### Task 2: Make The SBA Staging Union Explicit

- Outcome: Replace `select *` in `stg_sba_loans` with an explicit standardized
  column list for both 7(a) and 504 branches.
- Builds on or must preserve: the existing standardized output contract from
  `stg_sba_7a_loans` and `stg_sba_504_loans`.
- Existing logic to reuse or extend: the current shared column set emitted by
  both SBA staging models.
- Public contract or state/data change: no output column names, order, grain, or
  values should change.
- Likely files/modules:
  - `dbt/models/staging/sba/stg_sba_loans.sql`
  - related staging unit tests if a schema-contract assertion already exists.
- First command/check:
  - Compare compiled `stg_sba_loans` column names before and after the change.
- Verification command:
  - `scripts/run_dbt_local.sh build --select stg_sba_loans+`
  - `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py`
- Review focus:
  - Explicit columns match the exact standardized SBA staging contract.
  - No `select *` remains in the union.
  - The union is still compatible with both DuckDB and Snowflake SQL.
- Risk/rollback:
  - Risk is missing a standardized column; rollback is restoring `select *`.
- Stop/ask if:
  - 7(a) and 504 staging models no longer share the same standardized columns.

### Task 3: Benchmark And Decide Whether A Heavier Intermediate Model Is Needed

- Outcome: Compare cost after Tasks 1 and 2 against the materialization baseline
  before deciding whether to add a table-like SBA standardized intermediate.
- Builds on or must preserve: the dbt materialization policy from
  `docs/implementation/dbt_materialization_cost_optimization_plan.md`.
- Existing logic to reuse or extend: `make benchmark-local` and its `.tmp`
  benchmark artifacts.
- Public contract or state/data change: none.
- Verification command:
  - `make benchmark-local COMMAND="make dbt-build-local-full"`
  - `make benchmark-local COMMAND="make powerbi-refresh-local"`
  - `make powerbi-model-check`
- Review focus:
  - `fact_sba_loans` remains the slowest node or meaningfully improves.
  - Power BI row counts stay in the expected live-data shape.
  - `data/raw` disk delta remains `0` for dbt/Power BI runs.
- Decision rule:
  - If `fact_sba_loans` is still materially slow after the cleanup, create a
    separate plan for an `int_sba_loans_standardized` table experiment.
  - If the full dbt build remains comfortably fast, defer the heavier
    intermediate model to avoid overengineering.
- Stop/ask if:
  - Benchmark output shows a KPI row-count change, relationship-test failure, or
    WSL memory pressure similar to the earlier pre-materialization issue.

## Final Verification

- `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py tests/unit/test_dbt_project_setup.py`
- `scripts/run_dbt_local.sh build --select stg_sba_loans+ fact_sba_loans+`
- `make dbt-build-local-fast`
- `make benchmark-local COMMAND="make dbt-build-local-full"`
- `make powerbi-model-check`
- `git diff --check`

## Acceptance Criteria

- `fact_sba_loans` no longer joins dimensions solely to retrieve deterministic
  `lender_key` or `source_file_key`.
- Existing dbt relationship tests still preserve referential integrity for fact
  keys.
- `stg_sba_loans` uses explicit columns for its 7(a)/504 `union all`.
- `fact_sba_loans` row count, key null counts, and downstream BI row-count
  shape remain stable.
- Benchmark evidence is recorded before any heavier intermediate-table decision.

## Open Questions

- None for the lighter cleanup. A future intermediate-table experiment should be
  planned separately only if post-cleanup benchmarks show a remaining practical
  bottleneck.
