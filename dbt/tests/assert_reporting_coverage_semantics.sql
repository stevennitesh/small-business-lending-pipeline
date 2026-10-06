{{ config(tags=['critical']) }}
-- Comparable annual changes must not silently cross partial periods or LAUS omissions.
select 'sba_yoy' as failure, state_key, approval_year as year
from {{ ref('mart_lending_annual_state') }}
where not coalesce(is_comparable_yoy, false)
  and (approved_loan_amount_yoy_growth_pct is not null or comparable_prior_year_amount is not null)
union all
select 'laus_coverage', state_key, year
from {{ ref('mart_laus_annual_state') }}
where missing_month_count < 0
   or unexpected_month_count < 0
   or observed_month_count != observed_expected_month_count + unexpected_month_count
   or missing_month_count != expected_month_count - observed_expected_month_count
   or (annual_coverage_status in ('full_year', 'year_to_date', 'publisher_omission') and (missing_month_count != 0 or unexpected_month_count != 0))
   or expected_month_count + publisher_omitted_month_count != expected_elapsed_month_count
   or (is_comparable_annual and (observed_expected_month_count != 12 or unexpected_month_count != 0 or publisher_omitted_month_count != 0 or is_year_to_date))
union all
select 'final_status', cast(null as varchar), cast(null as integer)
from {{ ref('mart_pipeline_run_summary') }}
where latest_run_status != 'unknown'
