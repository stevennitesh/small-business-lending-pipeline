-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_name,
    approval_year,
    total_approved_loan_amount,
    loan_count,
    approval_amount_coverage_count,
    average_loan_size,
    approved_loan_amount_yoy_growth_pct,
    loan_count_yoy_growth_pct,
    comparable_prior_year_amount,
    is_comparable_yoy,
    is_full_calendar_year,
    calendar_period_status,
    first_observed_approval_date,
    last_observed_approval_date,
    source_calendar_start,
    source_calendar_end,
    coverage_evidence_as_of
from {{ ref('mart_lending_annual_state') }}
