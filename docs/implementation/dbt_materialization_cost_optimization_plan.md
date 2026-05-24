# Plan: Formalize DBT Materialization For Local Cost Reduction

## Summary

The best next dbt speedup is to formalize the materialization policy that has
already benchmarked well locally:

- keep staging models as views;
- materialize marts, dimensions, facts, context, lending, and BI models as
  tables;
- keep `make dbt-build-local-fast` as the iteration path with only critical BI
  contract tests;
- keep `make dbt-build-local-full` as the release-quality path with all tests.

This is the highest-confidence next move because the existing benchmark
evidence shows the main cost was repeated view recomputation during tests, not
dbt parsing or seed work.

## Analysis

### Current Evidence

The local command split and benchmark work already gives enough signal to avoid
guessing:

- Before table materialization, live local `make dbt-build-local-full` took
  about `313.8s` with about `10.2 GB` max RSS and only grew DuckDB by about
  `262 KB`.
- After materializing marts and BI models as tables, the same full build took
  about `31.6s` with about `8.5 GB` max RSS and grew DuckDB by about `220 MB`.
- Before materialization, live local `make dbt-build-local-fast` took about
  `58.9s` with about `10.0 GB` max RSS.
- After materialization, live local `make dbt-build-local-fast` took about
  `29.1s` with about `7.7 GB` max RSS.
- The tradeoff is clear: spend a few hundred MB of DuckDB disk to avoid
  repeatedly recomputing SBA-heavy views during tests and exports.

The current uncommitted `dbt/dbt_project.yml` already reflects this experiment:

- `staging`: `view`.
- `marts`: `table`.
- `marts.dimensions`, `marts.facts`, `marts.context`, `marts.lending`: `table`.
- `bi`: `table`.

That should become an intentional, tested project contract instead of a local
experiment.

### Refreshed Verification Evidence

Issue #105 refreshed the benchmark evidence on 2026-05-24 after PR #104 was
merged and local `master` was synchronized:

- `make benchmark-local COMMAND="make dbt-build-local-fast"` passed with
  `63.391s` wall time, `8,067,702,784` bytes max RSS, DuckDB size
  `653,537,280` bytes, and `0` byte `data/raw` delta.
- `make benchmark-local COMMAND="make dbt-build-local-full"` passed with
  `32.079s` wall time, `8,423,215,104` bytes max RSS, DuckDB size
  `654,848,000` bytes, and `0` byte `data/raw` delta.
- `make benchmark-local COMMAND="make powerbi-refresh-local"` passed with
  `29.902s` wall time, `8,106,180,608` bytes max RSS, DuckDB size
  `655,110,144` bytes, and `0` byte `data/raw` delta.
- Power BI refresh exported 17 BI CSV tables; key row counts stayed in the
  expected live-data shape, including `bi_executive_overview` at `1,887`,
  `bi_lender_mix` at `149,873`, `bi_industry_mix` at `31,733`,
  `bi_regional_business_health` at `1,734`, and `bi_year_filter` at `37`.
- `make powerbi-model-check` passed with 17 tables, 25 relationships, and
  filter coverage for industry, lender, program, region, state, and year.

### Why This Beats SQL Tuning First

SQL tuning individual models is less attractive as the next slice because:

- full dbt validation dropped from about five minutes to about thirty seconds
  without changing business SQL;
- most remaining wall-clock cost in fast mode is critical BI tests when models
  are views, and those tests become cheap once BI tables are materialized;
- model-specific SQL tuning risks changing KPI behavior, while materialization
  preserves model SQL semantics.

### Why This Beats More Test Splitting First

The project already has a useful test split:

- fast mode runs model creation plus `tag:critical`;
- critical tests are BI non-empty and BI grain checks;
- full mode keeps all relationship, reconciliation, and deeper data-quality
  tests.

More aggressive test slicing can still help later, but materialization makes
the existing full suite cheap enough that further slicing is not the biggest
win right now.

## Key Changes

### Task 1: Commit The Materialization Policy As A DBT Contract

- Apply the existing `dbt/dbt_project.yml` materialization policy deliberately:
  - staging models stay views;
  - marts and BI models become tables;
  - pipeline audit marts remain in the audit schema but inherit table
    materialization unless a specific reason appears during verification.
- Add unit coverage that parses `dbt/dbt_project.yml` and asserts the intended
  policy so future cleanup does not silently revert the cost boundary.
- Do not change SQL model logic, KPI definitions, source contracts, or Power BI
  export table names.

### Task 2: Benchmark And Record The Cost Tradeoff

- Run benchmark commands against the current live local DuckDB warehouse:
  - `make benchmark-local COMMAND="make dbt-build-local-fast"`.
  - `make benchmark-local COMMAND="make dbt-build-local-full"`.
  - `make benchmark-local COMMAND="make powerbi-refresh-local"`.
- Record the new wall time, max RSS, DuckDB size, and disk deltas in this plan
  or in `docs/implementation/local_pipeline_cost_boundary_plan.md`.
- Do not commit `.tmp/benchmarks/` artifacts.
- Keep the conclusion explicit: this optimization trades larger DuckDB tables
  for substantially lower repeated compute cost.

### Task 3: Tighten The Benchmark Helper If Needed

- If benchmark output still fails to show useful dbt slow-node timings, update
  `scripts/benchmark_local_command.py` and its unit tests so slow-node summaries
  reliably include `execution_time_seconds` from fresh `dbt/target/run_results.json`.
- Preserve the existing `data/raw` size bucket in `DEFAULT_SIZE_PATHS`.
- Keep benchmark output under `.tmp/benchmarks/`.

### Task 4: Verify Downstream Local BI Behavior

- Run:
  - `make dbt-local`.
  - `make dbt-build-local-fast`.
  - `make dbt-build-local-full`.
  - `make powerbi-refresh-local`.
  - `make powerbi-model-check`.
  - `.venv/bin/python -m pytest tests/unit/test_dbt_project_setup.py tests/unit/test_benchmark_local_command.py tests/unit/test_powerbi_model_contract.py`.
  - `git diff --check`.
- Compare Power BI export row counts to the current live baseline and confirm
  there is no KPI-shape change.
- Do not stage generated DuckDB, dbt target, benchmark, Power BI CSV, or PBIX
  artifacts.

## Implementation Notes

- Implement this after PR #104 is merged or rebase a new branch on top of it, so
  raw-load optimization and dbt materialization evidence do not drift.
- Use one GitHub issue for this slice unless the implementation reveals a
  separate benchmark-helper bug large enough to justify its own issue.
- Keep `powerbi/lending_dashboard.pbix` untouched.
- Keep the existing local/cloud separation:
  - local route uses DuckDB materialization;
  - cloud route should use the same dbt model materialization semantics in
    Snowflake unless a later cloud-cost decision overrides it.

## Acceptance Criteria

- `dbt/dbt_project.yml` declares the intended staging/view and marts/BI/table
  materialization policy.
- Unit tests protect the materialization policy.
- Fast and full dbt benchmark evidence is refreshed and recorded.
- Full dbt validation remains available and passes.
- Power BI refresh and model contract checks pass.
- No generated local artifacts or PBIX changes are committed.

## Assumptions

- The user prefers lower WSL memory/time cost over minimizing the DuckDB file by
  a few hundred MB.
- The current live DuckDB warehouse is representative enough for local
  benchmarking.
- No KPI SQL behavior should change in this optimization slice.
- Further SQL tuning is deferred until materialization is committed and the next
  benchmark identifies a specific slow model.
