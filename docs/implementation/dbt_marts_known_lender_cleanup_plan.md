# Plan: Exclude Unknown Lenders From Lender Calculations

## Goal

Update lender-specific dbt marts so unknown lenders do not participate in lender share, lender rank, lender count, or top-lender concentration calculations.

The intended contract is:

- overall lending totals still include all valid SBA loan records, including missing or unknown lender names;
- lender-specific analytics use known lenders only;
- BI lender mix and lender concentration outputs should not rank, count, or calculate concentration from the `UNKNOWN` lender bucket.

## Non-Goals

- Do not remove the `UNKNOWN` row from `dim_lender`.
- Do not remove `UNKNOWN` from `fact_sba_loans`; facts should still preserve missing-source lender information.
- Do not change program, industry, state trend, or executive overview lending totals.
- Do not add HHI or other optional concentration metrics.
- Do not modify the Power BI `.pbix` file in this cleanup.

## Constraints

- Preserve current local/cloud route-neutral dbt marts behavior.
- Keep rates and shares as decimal values for Power BI formatting.
- Keep the dashboard-facing column names stable where practical:
  - `lender_approved_amount_share`
  - `lender_count`
  - `top_1_lender_share`
  - `top_5_lender_share`
- Make the known-lender denominator explicit in schema docs and tests.
- Leave the unrelated local `powerbi/lending_dashboard.pbix` change untouched.

## Execution Mode

Execution mode: sequential.

This is a behavior change across overlapping marts/tests/docs, so implement it in one branch/workspace without parallel work.

## Baseline

- Current working tree has an unrelated local PBIX modification.
- Current behavior:
  - `fact_sba_loans` maps missing or unmatched lender names to `lender_key = 'UNKNOWN'`.
  - `mart_lending_lender_state_period` includes `UNKNOWN` in lender totals, shares, and ranks.
  - `mart_lending_concentration_state_period` derives top-1/top-5 concentration from `mart_lending_lender_state_period`, so `UNKNOWN` can be ranked and counted.
  - `bi_lender_mix` filters `UNKNOWN`, but this happens after upstream lender calculations already include it.
- Recent verification before this plan:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_context_marts.py tests/unit/test_dbt_bi_pipeline_models.py`
  - `make dbt-local`

## Acceptance Checks

- `mart_lending_lender_state_period` excludes `lender_key = 'UNKNOWN'` before aggregation, share calculation, and ranking.
- `lender_approved_amount_share` denominator is known-lender approved dollars for the state-year, not all approved dollars including unknown lenders.
- `mart_lending_concentration_state_period` derives `lender_count`, top-1, and top-5 concentration from known lenders only.
- `bi_lender_mix` still has no `UNKNOWN` lender rows.
- Existing annual lending totals remain inclusive and unchanged in `mart_lending_annual_state`.
- Reconciliation tests compare lender marts to fact rows filtered to known lenders.
- Schema docs make the known-lender denominator clear.
- The small `select *` cleanup in the concentration mart is handled by selecting explicit columns from the known-lender mart.

## GitHub Issues

- [#72 Exclude unknown lenders from lender share calculations](https://github.com/stevennitesh/small-business-lending-pipeline/issues/72)
- [#73 Use explicit known-lender inputs for concentration](https://github.com/stevennitesh/small-business-lending-pipeline/issues/73)
- [#74 Document BI known-lender semantics](https://github.com/stevennitesh/small-business-lending-pipeline/issues/74)

## Tasks

### Task 1: Filter unknown lenders at the lender mart boundary

- Outcome: `mart_lending_lender_state_period` aggregates only known lenders.
- Builds on or must preserve: `fact_sba_loans.lender_key`, `dim_lender.UNKNOWN`, and the existing state-year-lender grain.
- Existing logic to reuse or extend: current lender aggregation, share calculation, and rank logic.
- Public contract or state/data change: lender mart totals become known-lender totals; annual lending totals remain inclusive elsewhere.
- Likely files/modules:
  - `dbt/models/marts/lending/mart_lending_lender_state_period.sql`
  - `dbt/models/marts/lending/schema.yml`
  - `dbt/tests/assert_mart_lending_lender_state_period_reconciles.sql`
  - `tests/unit/test_dbt_lending_marts.py`
- Change boundary:
  - Add `fact.lender_key != 'UNKNOWN'` before lender aggregation.
  - Ensure share denominator comes from known-lender totals, not all annual totals.
  - Update reconciliation test to filter fact rows to known lenders.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
- Review focus:
  - Unknown lender rows are excluded before rank/share logic.
  - Shares reconcile to known-lender denominator.
- Risk/rollback:
  - Medium: BI lender totals will change where unknown lender volume exists. Roll back by restoring the current inclusive lender aggregation.
- Status: completed in #72

### Task 2: Make concentration use known-lender inputs explicitly

- Outcome: concentration counts and top-1/top-5 shares use known lenders only.
- Builds on or must preserve: Task 1's known-lender `mart_lending_lender_state_period` contract.
- Existing logic to reuse or extend: current top-1/top-5 concentration and ordering test.
- Public contract or state/data change: concentration totals and lender counts become known-lender totals/counts.
- Likely files/modules:
  - `dbt/models/marts/lending/mart_lending_concentration_state_period.sql`
  - `dbt/models/marts/lending/schema.yml`
  - `dbt/tests/assert_mart_lending_top_lender_share_ordering.sql`
  - `tests/unit/test_dbt_lending_marts.py`
- Change boundary:
  - Replace the current `select *` CTE with explicit known-lender columns.
  - Keep existing top-1 and top-5 output names.
  - Confirm `top_1_lender_share <= top_5_lender_share`.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
- Review focus:
  - No `UNKNOWN` rows can enter concentration through the source mart.
  - `lender_count` means known active lender count.
- Risk/rollback:
  - Low once Task 1 is correct; concentration already depends on the lender mart.
- Status: pending

### Task 3: Update BI docs/tests for known-lender semantics

- Outcome: BI-facing docs/tests make it clear that lender mix and concentration exclude unknown lenders.
- Builds on or must preserve: Tasks 1-2 known-lender mart contracts.
- Existing logic to reuse or extend: current `bi_lender_mix` unknown filter and `assert_bi_lender_mix_excludes_unknown.sql`.
- Public contract or state/data change: BI docs now describe known-lender calculations.
- Likely files/modules:
  - `dbt/models/bi/schema.yml`
  - `dbt/models/bi/bi_lender_mix.sql`
  - `dbt/models/bi/bi_lender_concentration.sql`
  - `dbt/tests/assert_bi_lender_mix_excludes_unknown.sql`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
- Change boundary:
  - Keep BI column names stable.
  - Keep the `bi_lender_mix` filter as a defensive guard even though upstream now excludes unknown lenders.
  - Add or update static tests so BI docs mention known-lender semantics.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_bi_pipeline_models.py`
- Review focus:
  - BI docs do not imply totals reconcile to all lending volume where unknown lenders exist.
- Risk/rollback:
  - Low; mostly docs/static tests.
- Status: pending

## Final Verification

Run focused tests:

```bash
.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py
```

Run broader marts/BI static checks:

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

- Should we later add an explicit data-quality metric such as `unknown_lender_approved_amount` or `unknown_lender_share` so dashboard users can see how much lending was excluded from known-lender concentration?
  - Recommendation: consider this during BI/pipeline-quality review, but keep it out of this cleanup unless the dashboard needs it immediately.
