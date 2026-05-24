# Plan: DBT Explicit Projection And Key Consistency Cleanup

## Goal

Make the dbt subsystem use one consistent contract for deterministic keys and
model projections instead of fixing one table at a time:

- fact models should generate deterministic `source_file_key` values from
  `raw_uri` the same way `dim_source_file` does;
- production dbt models should avoid wildcard projections such as `select *` or
  `alias.*` when those projections hide the model contract;
- existing relationship tests should continue to prove referential integrity.

## Non-goals

- Do not change KPI definitions, Power BI export contracts, source contracts,
  local/cloud route boundaries, or materialization policy.
- Do not rewrite dbt tests that intentionally return failing rows with
  `select *`.
- Do not add intermediate tables, incremental models, or environment-specific
  SQL.
- Do not stage or modify `powerbi/lending_dashboard.pbix`.

## Constraints

- Preserve row grain, column names, and BI row-count shape.
- Keep SQL portable across DuckDB and Snowflake targets.
- Keep staging as views and marts/BI as tables.
- Use relationship tests for referential integrity after deterministic keys are
  generated directly.

## Execution Mode

Execution mode: sequential

Parallel groups:
- None. Several slices touch related dbt models and tests; execute in order so
  each pass establishes the contract the next one protects.

## Baseline Evidence

Current workspace:

- Local `master` is synchronized to `origin/master` at merge commit `de321ba`.
- `powerbi/lending_dashboard.pbix` is dirty and user-owned; leave it unstaged.

Current failing signal:

- `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py` fails after
  the `fact_sba_loans` cleanup because the test still expects every fact model
  to join `dim_source_file`:
  - `fact_sba_loans` now generates `source_file_key` directly from `raw_uri`;
  - `fact_bds_state_year` and `fact_laus_state_month` still join
    `dim_source_file` only to retrieve the same deterministic key.

Current wildcard-projection findings in production dbt models:

- `dbt/models/staging/audit/stg_ingestion_manifest.sql`
  - `select *` in the manifest CTE.
- `dbt/models/staging/sba/stg_sba_7a_loans.sql`
  - `select *` in `latest_successful_manifests`;
  - `raw.*` in `raw_rows`;
  - `raw.*` in `source_rows`;
  - final `select * from standardized`.
- `dbt/models/staging/sba/stg_sba_504_loans.sql`
  - same wildcard patterns as `stg_sba_7a_loans`.
- `dbt/models/staging/census/stg_census_bds_state_year.sql`
  - `select *` in `latest_successful_manifests`;
  - `raw.*` in `raw_rows`.
- `dbt/models/staging/bls/stg_bls_laus_state_month.sql`
  - `select *` in `latest_successful_manifests`;
  - `raw.*` in `raw_rows`.
- `dbt/models/marts/facts/fact_sba_loans.sql`
  - `select *` in the `loans` CTE.
- `dbt/models/marts/context/mart_laus_annual_state.sql`
  - `annual.*` in the `with_context` CTE.
- `dbt/models/marts/lending/mart_lending_annual_state.sql`
  - `annual.*` in the `with_context` CTE.
- `dbt/models/marts/lending/mart_lending_monthly_state.sql`
  - `monthly.*` in the `with_context` CTE.
- `dbt/models/marts/lending/mart_lending_lender_state_period.sql`
  - `lender_period.*` in the `with_shares` CTE.
- `dbt/models/bi/bi_executive_overview.sql`
  - `select *` in the `lending` CTE.

Patterns intentionally not included:

- `dbt/tests/*.sql` and `dbt/macros/generic_tests.sql` use `select *` to return
  failing rows for dbt tests. That is acceptable test behavior, not a production
  model projection contract.
- `count(*)` and arithmetic such as `loan_count * 1000.0` are not wildcard
  projections.
- Dimension joins used for labels or semantic mapping should stay. Examples:
  state/lender/program/NAICS display joins in marts and BI models. The cleanup
  only targets joins that exist solely to retrieve deterministic keys.

## Tasks

### Task 1: Normalize Deterministic Source-File Keys Across Fact Models

- Outcome: All fact models generate `source_file_key` directly from `raw_uri`
  using `generate_surrogate_key(["raw_uri"])`, matching `dim_source_file`.
- Builds on or must preserve:
  - `dim_source_file` remains the source lineage dimension.
  - Existing schema relationship tests still validate fact keys against
    `dim_source_file`.
  - `fact_sba_loans` direct-key behavior from PR #110.
- Existing logic to reuse or extend:
  - `dim_source_file.sql` key expression:
    `{{ generate_surrogate_key(["raw_uri"]) }} as source_file_key`.
  - `fact_sba_loans.sql` direct `source_file_key` generation.
- Public contract or state/data change: no output column names, grains, or KPI
  semantics should change.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_bds_state_year.sql`
  - `dbt/models/marts/facts/fact_laus_state_month.sql`
  - `tests/unit/test_dbt_marts_models.py`
- Change boundary:
  - Remove the `dim_source_file` lookup joins from BDS and LAUS facts only when
    they are used solely to retrieve `source_file_key`.
  - Update the stale unit test from "facts join source file dimension" to
    "facts generate source file keys deterministically and schema tests preserve
    relationships."
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py` should
    fail before the fix and pass after the fix.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py`
  - `scripts/run_dbt_local.sh build --select fact_bds_state_year+ fact_laus_state_month+ fact_sba_loans+`
- Review focus:
  - Source-file keys are generated from `raw_uri` in every fact model.
  - Relationship tests still exist in `dbt/models/marts/schema.yml`.
  - No dimension display or semantic mapping joins are removed.
- Risk/rollback:
  - Risk is source lineage key mismatch; rollback is restoring the source-file
    joins.
- Stop/ask if:
  - Any fact model needs a non-`raw_uri` source-file identity.
- Status: completed in issue #111 / commit `6f70268`

### Task 2: Add A Production-Model Wildcard Projection Guard

- Outcome: Unit coverage makes the no-hidden-projection policy explicit for
  production dbt models.
- Builds on or must preserve:
  - Existing tests that allow dbt test SQL to return failing rows.
  - `tests/unit/test_dbt_staging_models.py` already protects
    `stg_sba_loans` from reverting to `select *`.
- Existing logic to reuse or extend:
  - Existing file-inspection unit tests in `tests/unit/test_dbt_*`.
- Public contract or state/data change: none; test-only guardrail.
- Likely files/modules:
  - `tests/unit/test_dbt_sql_contracts.py` or the closest existing dbt unit
    test file.
- Change boundary:
  - Scan `dbt/models/**/*.sql` only.
  - Flag true wildcard projections: `select *`, standalone `*` immediately
    after `select`, and `alias.*`.
  - Do not flag `count(*)`, multiplication, dbt tests, or generic test macros.
- First command/check:
  - New guard should fail before projection cleanup, proving it detects the
    current production-model findings.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_sql_contracts.py`
  - or the updated focused dbt unit test file.
- Review focus:
  - Guard catches the current production-model wildcard findings.
  - Guard does not create noisy false positives for `count(*)` or dbt test SQL.
- Risk/rollback:
  - Risk is an overbroad static test; rollback is narrowing the matcher.
- Stop/ask if:
  - The matcher requires SQL parsing complexity beyond a focused file-pattern
    guard.
- Status: completed in issue #112 / commit `2f745dd`

### Task 3: Make Staging Source And Manifest Projections Explicit

- Outcome: Staging models list the manifest and raw source columns they depend
  on instead of carrying full source rows through `*` projections.
- Builds on or must preserve:
  - Route-neutral `raw_uri`/`storage_backend` handoff.
  - Latest-successful manifest filtering.
  - Raw source row identity for SBA row numbering.
- Existing logic to reuse or extend:
  - Current source-specific standardization SQL.
  - Existing staging schema tests and source identity tests.
- Public contract or state/data change: no staged output columns or row grain
  should change.
- Likely files/modules:
  - `dbt/models/staging/audit/stg_ingestion_manifest.sql`
  - `dbt/models/staging/sba/stg_sba_7a_loans.sql`
  - `dbt/models/staging/sba/stg_sba_504_loans.sql`
  - `dbt/models/staging/census/stg_census_bds_state_year.sql`
  - `dbt/models/staging/bls/stg_bls_laus_state_month.sql`
  - staging unit tests touched only as needed.
- Change boundary:
  - Replace `select *` in manifest CTEs with the fields used for filtering and
    joins.
  - Replace `raw.*` CTEs with explicit raw source fields plus lineage metadata.
  - Replace SBA final `select * from standardized` with the same explicit
    standardized column contract used by `stg_sba_loans`.
- First command/check:
  - Run the production-model wildcard guard from Task 2 to confirm these
    models are the remaining staging offenders.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_staging_models.py`
  - `scripts/run_dbt_local.sh build --select stg_ingestion_manifest+ stg_sba_7a_loans+ stg_sba_504_loans+ stg_census_bds_state_year+ stg_bls_laus_state_month+`
- Review focus:
  - Raw and manifest fields needed by source standardization are all present.
  - `raw_uri` and `storage_backend` remain route-neutral lineage identities.
  - SBA 7(a), SBA 504, Census, and BLS staging behavior stays source-specific
    but follows the same projection discipline.
- Risk/rollback:
  - Risk is accidentally omitting a source column used by standardization;
    rollback is restoring the narrower model file.
- Stop/ask if:
  - A raw source column exists in one route but not the other and needs a source
    contract decision.
- Status: completed in issue #113 / commit `0db522a`

### Task 4: Make Fact, Mart, And BI Derived Projections Explicit

- Outcome: Remaining production marts and BI models stop carrying hidden
  wildcard projections through internal CTEs.
- Builds on or must preserve:
  - Deterministic-key policy from Task 1.
  - Wildcard guard from Task 2.
  - Current mart and BI output contracts.
- Existing logic to reuse or extend:
  - Current final `select` lists, relationship tests, reconciliation tests, and
    Power BI model contract checks.
- Public contract or state/data change: no mart/BI output columns, grains, or
  KPI values should change.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_sba_loans.sql`
  - `dbt/models/marts/context/mart_laus_annual_state.sql`
  - `dbt/models/marts/lending/mart_lending_annual_state.sql`
  - `dbt/models/marts/lending/mart_lending_monthly_state.sql`
  - `dbt/models/marts/lending/mart_lending_lender_state_period.sql`
  - `dbt/models/bi/bi_executive_overview.sql`
  - mart/BI unit tests touched only as needed.
- Change boundary:
  - Replace `select *`, `annual.*`, `monthly.*`, and `lender_period.*` with
    explicit columns in production model CTEs.
  - Keep joins that add display labels or semantic dimension attributes.
- First command/check:
  - Run the production-model wildcard guard from Task 2 to list remaining
    offenders after Task 3.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py`
  - `scripts/run_dbt_local.sh build --select fact_sba_loans+ mart_laus_annual_state+ mart_lending_annual_state+ mart_lending_monthly_state+ mart_lending_lender_state_period+ bi_executive_overview+`
- Review focus:
  - Internal CTEs are explicit but final outputs stay unchanged.
  - Mart reconciliation tests still pass.
  - BI contract remains compatible with Power BI exports.
- Risk/rollback:
  - Risk is missing a derived field used by a downstream CTE; rollback is
    restoring the affected model file.
- Stop/ask if:
  - A model output contract must change to remove a wildcard.
- Status: completed in issue #114 / commit `eafd1bd`

### Task 5: Run End-To-End DBT/BI Consistency Checks

- Outcome: Confirm the cleanup is behavior-preserving and the repo-wide policy
  is enforced.
- Builds on or must preserve:
  - All earlier tasks.
  - Local/cloud shared dbt SQL.
- Existing logic to reuse or extend:
  - Fast dbt mode, full dbt benchmark, and Power BI model checks.
- Public contract or state/data change: none.
- Likely files/modules:
  - Plan document only if benchmark or verification evidence should be recorded.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_staging_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_dbt_project_setup.py`
  - `make dbt-build-local-fast`
  - `make powerbi-model-check`
  - `git diff --check`
- Optional when WSL has enough memory headroom:
  - `make benchmark-local COMMAND="make dbt-build-local-full"`
  - `make benchmark-local COMMAND="make powerbi-refresh-local"`
- Review focus:
  - No production dbt model wildcard projections remain.
  - Fact models all use deterministic source-file key generation.
  - Relationship tests still protect referential integrity.
  - Generated dbt/benchmark/Power BI artifacts and the PBIX are not committed.
- Risk/rollback:
  - Risk is test runtime or WSL memory pressure; rollback is to focused checks
    plus optional benchmark deferral.
- Stop/ask if:
  - Full benchmark shows memory pressure similar to earlier WSL crashes.
- Status: completed in issue #115

## Final Verification

Required:

- `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_staging_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_dbt_project_setup.py`
- `make dbt-build-local-fast`
- `make powerbi-model-check`
- `git diff --check`

Completed evidence on 2026-05-24:

- `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_staging_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_dbt_project_setup.py`
  passed with 37 tests.
- `make dbt-build-local-fast` passed with seed PASS=4, model run PASS=51,
  and critical test PASS=33.
- `make powerbi-model-check` passed with 17 tables, 25 relationships, and
  filter coverage for industry, lender, program, region, state, and year.
- `git diff --check` passed before final evidence was recorded.

Optional when WSL has enough memory headroom:

- `make benchmark-local COMMAND="make dbt-build-local-full"`
- `make benchmark-local COMMAND="make powerbi-refresh-local"`

## Acceptance Criteria

- All fact models generate `source_file_key` from `raw_uri` consistently.
- `dim_source_file` remains the relationship target for source lineage.
- Production dbt models under `dbt/models` have no hidden wildcard
  projections.
- Test SQL under `dbt/tests` may still return failing rows with `select *`.
- Existing dbt relationship and reconciliation tests still pass.
- Power BI model contract remains valid.

## Open Questions

- None before implementation. If the wildcard guard produces false positives
  during implementation, narrow the matcher rather than weakening the production
  model policy.
