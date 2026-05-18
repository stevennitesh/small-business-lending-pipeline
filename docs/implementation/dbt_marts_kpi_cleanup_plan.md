# Plan: Finish dbt Marts KPI Cleanup

## Goal

Clean up the remaining low-risk dbt marts issues found after the staging-to-marts handoff review:

- centralize the annual SBA approval-year rule;
- strengthen mart schema documentation for KPI outputs;
- add top-1 lender concentration alongside the existing top-5 lender concentration.

The marts layer should stay route-neutral. Local and cloud differences should remain lineage metadata or adapter SQL dialect differences, not separate business logic.

## Non-Goals

- Do not redesign mart grains.
- Do not move KPI logic into Power BI.
- Do not split local and cloud marts.
- Do not change extraction, raw validation, raw load, or staging contracts.
- Do not add HHI or other optional concentration metrics in this pass.

## Constraints

- Preserve current dashboard-facing values except for the approved addition of top-1 lender concentration fields.
- Keep facts and marts consuming staged contracts or upstream marts only; no raw-source reads in marts or BI.
- Keep rates and shares as decimal values for Power BI formatting.
- Leave `powerbi/lending_dashboard.pbix` untouched unless the user explicitly asks to update the dashboard file.

## Execution Mode

Execution mode: sequential.

This cleanup is small and touches overlapping dbt model/test/docs files, so it should be implemented by one agent in one branch.

## Baseline

- Current working tree has an unrelated local PBIX modification.
- Focused marts checks passed before this plan:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_context_marts.py tests/unit/test_dbt_bi_pipeline_models.py`
  - `make dbt-local`
- Current evidence:
  - `dbt/models/marts` and `dbt/models/bi` no longer read `source('raw', ...)`.
  - `approval_year` is calculated repeatedly in lending marts and reconciliation tests with:
    `coalesce(extract(year from approval_date)::integer, approval_fiscal_year)`.
  - `README.md` mentions top-1 lender share, while the current marts only expose top-5 lender share.

## Acceptance Checks

- `fact_sba_loans` exposes one canonical `approval_year` field.
- Lending marts reuse `fact_sba_loans.approval_year` instead of repeating the approval-date/fiscal-year fallback expression.
- Reconciliation tests use the same canonical fact `approval_year` field.
- `mart_lending_concentration_state_period` exposes:
  - `top_1_approved_loan_amount`
  - `top_1_lender_share`
  - `top_5_approved_loan_amount`
  - `top_5_lender_share`
- BI lender concentration exposes top-1 and top-5 concentration fields.
- Schema docs/tests document important mart KPI columns, including average loan size, YoY fields, and top-1/top-5 lender concentration.
- `make dbt-local` passes.

## GitHub Issues

- [#68 Centralize SBA approval year in fact model](https://github.com/stevennitesh/small-business-lending-pipeline/issues/68)
- [#69 Reuse canonical approval year in lending marts](https://github.com/stevennitesh/small-business-lending-pipeline/issues/69)
- [#70 Add top-1 lender concentration metric](https://github.com/stevennitesh/small-business-lending-pipeline/issues/70)
- [#71 Strengthen dbt marts KPI docs and checks](https://github.com/stevennitesh/small-business-lending-pipeline/issues/71)

## Tasks

### Task 1: Centralize SBA approval-year logic in the fact model

- Outcome: `fact_sba_loans` has a canonical `approval_year` column.
- Builds on or must preserve: existing `approval_date`, `approval_fiscal_year`, and fact grain.
- Existing logic to reuse or extend: the repeated expression in annual/lender/industry/program lending marts.
- Public contract or state/data change: adds a modeled fact column; does not remove existing columns.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_sba_loans.sql`
  - `dbt/models/marts/schema.yml`
  - `tests/unit/test_dbt_marts_models.py`
- Change boundary: add the canonical field and docs/tests only.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py`
- Review focus: confirm the expression is exactly the prior fallback rule.
- Risk/rollback: low; remove the field and related tests if dbt compile fails.
- Status: completed in #68 (`876b507`)

### Task 2: Reuse canonical approval_year in lending marts and tests

- Outcome: annual and period lending marts use `fact_sba_loans.approval_year`.
- Builds on or must preserve: Task 1's `approval_year` field.
- Existing logic to reuse or extend: current lending mart aggregation, shares, ranks, and reconciliation tests.
- Public contract or state/data change: preserves existing mart columns and values.
- Likely files/modules:
  - `dbt/models/marts/lending/mart_lending_annual_state.sql`
  - `dbt/models/marts/lending/mart_lending_lender_state_period.sql`
  - `dbt/models/marts/lending/mart_lending_industry_state_period.sql`
  - `dbt/models/marts/lending/mart_lending_program_state_period.sql`
  - `dbt/tests/assert_mart_lending_annual_state_reconciles.sql`
  - `tests/unit/test_dbt_lending_marts.py`
- Change boundary: replace duplicated expressions, do not change grain or filters.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
- Review focus: annual totals still reconcile to facts.
- Risk/rollback: medium-low; duplicated expression can be restored if compile or reconciliation behavior changes unexpectedly.
- Status: completed in #69

### Task 3: Add top-1 lender concentration alongside top-5

- Outcome: lender concentration marts and BI expose both top-1 and top-5 lender share.
- Builds on or must preserve: existing lender ranking from `mart_lending_lender_state_period`.
- Existing logic to reuse or extend: `lender_rank` and current `top_5_approved_loan_amount` calculation.
- Public contract or state/data change: adds new mart/BI columns; preserves current top-5 columns.
- Likely files/modules:
  - `dbt/models/marts/lending/mart_lending_concentration_state_period.sql`
  - `dbt/models/marts/lending/schema.yml`
  - `dbt/models/bi/bi_lender_concentration.sql`
  - `dbt/models/bi/schema.yml`
  - `dbt/tests/assert_mart_lending_top_lender_share_ordering.sql`
  - `tests/unit/test_dbt_lending_marts.py`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
  - `README.md`
- Change boundary: add top-1 fields and tests; do not add HHI or additional top-N metrics.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py`
- Review focus: `top_1_lender_share <= top_5_lender_share` and both shares remain between 0 and 1.
- Risk/rollback: low; remove the added top-1 columns/tests if the dashboard contract should stay top-5 only.
- Status: completed in #70

### Task 4: Strengthen marts KPI documentation and static tests

- Outcome: mart schema docs cover the important KPI columns consistently.
- Builds on or must preserve: Tasks 1-3 column contracts.
- Existing logic to reuse or extend: current `schema.yml` docs and pytest schema assertions.
- Public contract or state/data change: docs/tests only, no SQL behavior change.
- Likely files/modules:
  - `dbt/models/marts/lending/schema.yml`
  - `dbt/models/marts/context/schema.yml`
  - `dbt/models/marts/pipeline/schema.yml`
  - `tests/unit/test_dbt_lending_marts.py`
  - `tests/unit/test_dbt_context_marts.py`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
- Change boundary: document existing output columns and add static checks for required docs/tests.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_context_marts.py tests/unit/test_dbt_bi_pipeline_models.py`
- Review focus: documentation matches actual SQL columns and does not promise unsupported metrics.
- Risk/rollback: low; docs-only changes are easy to revert.
- Status: completed in #71

## Final Verification

Run focused tests:

```bash
.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_context_marts.py tests/unit/test_dbt_bi_pipeline_models.py
```

Run dbt compile:

```bash
make dbt-local
```

Finish with:

```bash
git diff --check
```

## Open Questions

- Should Power BI immediately use the new `top_1_lender_share`, or should we only expose it in the BI table for now and update visuals later?
- Should top-1 be labeled in Power BI as "Top lender share" or "Top 1 lender share"? Recommendation: use "Top lender share" for visual labels and keep `top_1_lender_share` as the column name.
