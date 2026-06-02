# Plan: Optimize `fact_sba_loans` Without Intermediate Tables

## Goal

Reduce the remaining local dbt cost around `fact_sba_loans` without adding the
wide SBA intermediate table that benchmarked worse than the current design.

The plan keeps the current materialization policy:

- staging stays as views;
- marts, facts, dimensions, and BI models stay as tables;
- `fact_sba_loans` remains the loan-grain source for downstream marts.

## Why Not An Intermediate Table

The temporary `int_sba_loans_standardized` A/B test showed the intermediate
table was not worth keeping:

- it reduced `fact_sba_loans` itself by about four seconds;
- it added a new 14-15 second same-grain table build;
- it increased the DuckDB warehouse by hundreds of MB;
- full and Power BI refresh benchmarks both got slower overall.

That means the next useful work should focus on the fact model and the repeated
staging work it forces, not on persisting a broad same-grain copy of SBA
staging.

## Non-goals

- Do not add `int_sba_loans_standardized` or another wide same-grain SBA
  intermediate table.
- Do not change KPI definitions, Power BI export contracts, or report visuals.
- Do not remove auditability from the modeled warehouse without a separate
  contract decision.
- Do not change the local/cloud route split: local uses DuckDB, cloud uses
  Snowflake, and both use dbt for modeled SQL.
- Do not optimize Snowflake-specific physical layout, clustering, or warehouse
  sizing in this slice.

## Constraints

- Preserve the one-row-per-SBA-loan grain of `fact_sba_loans`.
- Preserve referential integrity through dbt relationship tests.
- Preserve local and cloud compatibility for dbt SQL.
- Keep generated DuckDB files, dbt target files, Power BI CSVs, benchmark JSON,
  and `powerbi/lending_dashboard.pbix` uncommitted.
- Use benchmarks against the real local DuckDB path before claiming a speed,
  memory, or disk improvement.

## Baseline

Latest measured behavior after rejecting the intermediate table:

- `make dbt-build-local-full`: about `31.4s`, max RSS about `7.7 GB`, DuckDB
  size about `654 MB`.
- `make powerbi-refresh-local`: about `30.6s`, max RSS about `8.2 GB`, DuckDB
  size about `655 MB`.
- `scripts/run_dbt_local.sh run`: about `19.3s`, max RSS about `7.6 GB`.
- Slowest dbt node remains `fact_sba_loans`, around `11.2s` to `11.9s`.

Current source shape:

- `fact_sba_loans` reads `stg_sba_loans`.
- `stg_sba_loans` expands `stg_sba_7a_loans` and `stg_sba_504_loans`.
- SBA staging computes `raw_row_number` with a window function over raw source
  rows.
- `fact_sba_loans` now generates deterministic `lender_key` and
  `source_file_key` directly, so the earlier expensive dimension key lookups
  are already gone.

Fresh baseline captured before this targeted optimization:

- `scripts/run_dbt_local.sh build --select fact_sba_loans+`: passed with
  `PASS=177`; `fact_sba_loans` built in about `12.56s`.
- `make benchmark-local COMMAND="scripts/run_dbt_local.sh run"`:
  wall time about `19.69s`, max RSS about `7.33 GB`, `fact_sba_loans` about
  `12.06s`.
- `make benchmark-local COMMAND="make dbt-build-local-full"`:
  wall time about `29.01s`, max RSS about `7.65 GB`, `fact_sba_loans` about
  `11.90s`.
- `fact_sba_loans` contract counters: `2,174,502` rows, `2,174,502`
  distinct fact keys, no null lender/source-file/NAICS keys, `225,770`
  `UNKNOWN` NAICS rows, and `109,190` `UNKNOWN` lender rows.

## Recommended Direction

There are two useful paths, and they should be measured separately.

1. Fact-only cleanup: simplify cheap derived-key work inside `fact_sba_loans`
   while preserving the public fact contract.
2. Raw-row-number propagation: move raw row numbering to raw load so SBA staging
   no longer recomputes a sort/window every time downstream dbt models expand
   the staging view.

The second path is the bigger likely win, but it crosses raw load and staging.
It should be implemented only after a small proof shows the row-number handoff
can stay identical across local DuckDB and cloud Snowflake routes.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. The same fact/staging/raw-load contract is involved, so each task
  should land with evidence before the next task changes the next boundary.

## Tasks

### Task 1: Lock The Current Fact Contract And Benchmark Baseline

- Outcome: Create repeatable evidence for current `fact_sba_loans` shape,
  row counts, key null counts, and slow-node timing before changing SQL.
- Builds on or must preserve: current materialization policy and existing dbt
  fact relationship tests.
- Existing logic to reuse or extend:
  - `make benchmark-local`.
  - `scripts/run_dbt_local.sh build --select fact_sba_loans+`.
  - existing dbt schema tests for `fact_sba_loans`.
- Public contract or state/data change: none.
- Likely files/modules:
  - `docs/implementation/fact_sba_loans_targeted_optimization_plan.md`.
  - tests only if current fact contract coverage has an obvious gap.
- First command/check:
  - `scripts/run_dbt_local.sh build --select fact_sba_loans+`.
- Verification command:
  - `make benchmark-local COMMAND="scripts/run_dbt_local.sh run"`.
  - `make benchmark-local COMMAND="make dbt-build-local-full"`.
- Review focus:
  - Baseline captures wall time, max RSS, DuckDB size, and dbt slow-node
    summary.
  - Baseline records fact row count and important key null counts.
- Risk/rollback:
  - No source behavior should change in this task.
- Stop/ask if:
  - Current `fact_sba_loans` tests or benchmark commands fail before any source
    edits.
- Status: complete. Baseline was captured before source edits.

### Task 2: Try The Small Fact-Only Cleanup

- Outcome: Remove any remaining avoidable work inside `fact_sba_loans` that
  does not require a new model layer.
- Builds on or must preserve: Task 1 baseline and existing fact output columns.
- Existing logic to reuse or extend:
  - current deterministic key generation in `fact_sba_loans`;
  - `dim_naics` key semantics;
  - existing relationship tests from fact keys to dimensions.
- Candidate changes:
  - compute `naics_key` directly from `naics_code` instead of joining
    `dim_naics` only to retrieve the same sector key;
  - keep the `dim_naics` relationship test so referential integrity still proves
    every generated `naics_key` exists;
  - inspect `approval_date_key` generation and only replace it with a cheaper
    cross-target expression if the change is small, clear, and tested.
- Public contract or state/data change:
  - no column names, grain, KPI definitions, or expected values should change.
- Depends on: Task 1.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_sba_loans.sql`.
  - `dbt/macros/` only if date-key generation is changed through a shared macro.
  - focused dbt SQL contract tests if needed.
- First command/check:
  - `scripts/run_dbt_local.sh build --select fact_sba_loans+`.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_sql_contracts.py tests/unit/test_dbt_project_setup.py`.
  - `scripts/run_dbt_local.sh build --select fact_sba_loans+`.
  - `make benchmark-local COMMAND="scripts/run_dbt_local.sh run"`.
- Review focus:
  - `naics_key` generation exactly matches `dim_naics`.
  - Unknown NAICS behavior stays unchanged.
  - Relationship tests still protect dimension integrity.
  - The benchmark shows whether the cleanup is meaningful or merely a
    readability improvement.
- Risk/rollback:
  - Risk is silent key drift. Rollback is restoring the tiny dimension lookup.
- Stop/ask if:
  - Direct key logic cannot be made obviously identical to the dimension, or
    benchmark evidence shows worse performance.
- Status: complete. Direct `naics_key` derivation preserved row counts and key
  parity, including `2,174,502` rows and no key nulls. A clean A/B rerun after
  WSL recovered measured the original `dim_naics` lookup at about `21.33s` wall
  time with `fact_sba_loans` around `12.69s`, then measured the direct-key
  version at about `20.03s` wall time with `fact_sba_loans` around `11.85s`.
  The direct-key version was retained as a small fact-model cost reduction.

### Task 3: Prove Raw Row Number Can Be Loaded Instead Of Recomputed

- Outcome: Determine whether raw load can persist a stable row number for SBA
  rows so staging can read it directly.
- Builds on or must preserve: DuckDB-native local raw load and Snowflake
  S3-stage cloud raw load.
- Existing logic to reuse or extend:
  - `pipelines/load/duckdb_loader.py` for local raw tables.
  - `pipelines/load/snowflake_loader.py` for cloud raw tables.
  - SBA staging models that currently compute `raw_row_number`.
- Public contract or state/data change:
  - add a raw lineage column only if both local and cloud routes can provide it
    consistently.
- Depends on: Task 1. It can run after Task 2, but it is conceptually separate.
- Likely files/modules:
  - `pipelines/load/duckdb_loader.py`.
  - `pipelines/load/snowflake_loader.py`.
  - `pipelines/load/raw_load_metadata.py`.
  - `dbt/models/staging/sba/stg_sba_7a_loans.sql`.
  - `dbt/models/staging/sba/stg_sba_504_loans.sql`.
  - loader and staging tests.
- First command/check:
  - Run a small local proof against fixture raw files to confirm the DuckDB
    native CSV scan can expose or assign stable file-row ordinality.
- Verification command:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py tests/unit/test_snowflake_loader.py`.
  - `scripts/run_dbt_local.sh build --select stg_sba_loans+ fact_sba_loans+`.
- Review focus:
  - Local route must not load all SBA CSVs into pandas just to number rows.
  - Cloud route should use Snowflake stage metadata or an equivalent
    cloud-native row-numbering method.
  - Existing fact keys and source file keys remain stable.
  - Row numbering is deterministic per source file, not dependent on an
    unordered warehouse scan.
- Risk/rollback:
  - Risk is changing loan-record keys if `raw_row_number` differs from the old
    staging computation. Rollback is keeping staging-owned row numbering.
- Stop/ask if:
  - DuckDB and Snowflake cannot produce comparable stable source-file row
    numbers without widening the raw-load contract beyond this plan.
- Status: rejected. A proof loaded `raw_row_number` in both local DuckDB and
  Snowflake loader SQL, then rebuilt `stg_sba_loans+ fact_sba_loans+`. Row
  counts stayed equal, but fact-key parity failed: `2,058,678` keys appeared
  only in the baseline and `2,058,678` only after the change. The current
  staging row number is a deterministic ordinal over the joined latest-manifest
  source rows, not a safely replaceable load-time row ordinal. The raw-load and
  staging changes were rolled back. During this proof, the local DuckDB loader
  also exposed a separate compatibility bug: DuckDB inferred Hive partition
  columns such as `pipeline_run_id` from raw artifact folders and collided with
  explicit raw metadata. The accepted fix is to disable Hive partition
  inference for native SBA CSV scans; this does not change the raw contract.

### Task 4: Replace The Staging Window Only If Row Number Parity Is Proven

- Outcome: Update SBA staging to read the loaded raw row number instead of
  recomputing `row_number() over (...)`.
- Builds on or must preserve: Task 3 row-number proof and current
  `loan_record_key` stability.
- Existing logic to reuse or extend:
  - current `loan_record_key` construction;
  - current raw metadata columns;
  - existing SBA staging explicit column contract.
- Public contract or state/data change:
  - modeled row counts and keys should stay stable;
  - raw tables gain one lineage field if Task 3 proves it.
- Depends on: Task 3.
- Likely files/modules:
  - SBA staging models.
  - dbt schema docs if raw column contracts are documented.
  - loader tests to verify raw row number presence.
- First command/check:
  - Compare old and new `loan_record_key` counts, distinct counts, and mismatch
    counts in a temporary A/B run.
- Verification command:
  - `scripts/run_dbt_local.sh build --select stg_sba_loans+ fact_sba_loans+`.
  - `make dbt-build-local-fast`.
  - `make benchmark-local COMMAND="scripts/run_dbt_local.sh run"`.
- Review focus:
  - No key churn.
  - No row-count change.
  - Staging no longer has the expensive row-number window.
  - Benchmark confirms whether the change helps enough to keep.
- Risk/rollback:
  - Risk is key churn or route-specific ordering differences. Rollback is
    restoring staging row-number computation.
- Stop/ask if:
  - Any `loan_record_key` mismatch appears against the baseline.
- Status: rejected. The staging window removal depends on Task 3 parity, and
  the loaded row-number proof produced large `loan_record_key` churn. The
  staging-owned `row_number() over (...)` remains the correct MVP behavior.

### Task 5: Decide Whether To Slim The Fact Contract

- Outcome: Make a deliberate decision on whether to keep all current fact
  columns or move rarely used descriptive fields into a separate detail table.
- Builds on or must preserve: downstream marts, BI export contracts, and audit
  expectations.
- Existing logic to reuse or extend:
  - current downstream marts that read `fact_sba_loans`;
  - dbt documentation and schema tests;
  - Power BI export contract checks.
- Public contract or state/data change:
  - this task should be analysis-first; any column removal or detail-table
    split requires explicit acceptance because it changes the mart contract.
- Depends on: Tasks 1 and 2. It does not depend on raw row-number work.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_sba_loans.sql`.
  - `dbt/models/marts/schema.yml`.
  - downstream mart SQL under `dbt/models/marts/`.
  - Power BI export/model contract tests if BI fields are affected.
- First command/check:
  - Scan all downstream dbt references to `fact_sba_loans` columns and classify
    columns as used by marts, tested/audit-only, or apparently unused.
- Verification command:
  - `make dbt-local`.
  - `make dbt-build-local-fast`.
  - `make powerbi-model-check`.
- Review focus:
  - Do not confuse "unused by current marts" with "safe to delete"; audit and
    traceability fields may be deliberately retained.
  - Prefer a separate plan before making destructive fact-contract changes.
- Risk/rollback:
  - Risk is breaking BI/report assumptions or reducing auditability. Rollback is
    keeping the wide fact table.
- Stop/ask if:
  - A proposed slim fact would remove a field that is part of the MVP audit or
    Power BI contract.
- Status: complete. Downstream marts use the fact for aggregations by state,
  year/month, program, lender, NAICS, status group, terms/pricing, charge-off,
  and jobs-supported metrics. Several descriptive and lineage columns are not
  directly consumed by current marts, but they preserve loan-level auditability
  and the fact model is not exposed directly to Power BI. No fact columns were
  removed in this slice. A future slim/detail split should be a separate
  contract change only if benchmarks show fact width is a dominant cost after
  the current local dbt path is otherwise stable.

## Final Verification

Run the final checks that match the tasks actually implemented:

- `.venv/bin/python -m pytest tests/unit/test_dbt_sql_contracts.py tests/unit/test_dbt_project_setup.py`.
- `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py tests/unit/test_snowflake_loader.py` if raw row-number work is included.
- `scripts/run_dbt_local.sh build --select stg_sba_loans+ fact_sba_loans+`.
- `make dbt-build-local-fast`.
- `make benchmark-local COMMAND="scripts/run_dbt_local.sh run"`.
- `make benchmark-local COMMAND="make dbt-build-local-full"`.
- `make powerbi-model-check`.
- `git diff --check`.

## Acceptance Criteria

- No wide same-grain SBA intermediate table is introduced.
- Any fact-only SQL cleanup preserves row counts, key null counts, unknown
  behavior, relationship tests, and downstream BI shape.
- Raw row-number propagation is implemented only if local and cloud routes can
  produce stable, comparable source-file row numbers.
- Staging row-number window removal is kept only if loan keys remain stable and
  benchmark evidence improves the local dbt path.
- Any fact-contract slimming is explicitly approved after downstream/audit usage
  is classified.
- Benchmark evidence is recorded before claiming speed, memory, or disk
  improvement.

## Open Questions

- The current staging row number is not interchangeable with a load-time CSV
  row ordinal without changing `loan_record_key`; keep staging-owned row
  numbering unless a future migration intentionally changes the key contract.
- High-cardinality descriptive fields in `fact_sba_loans` currently function as
  loan-level audit fields. Split them only under a separate approved plan with
  benchmark evidence and Power BI/dbt contract updates.
