-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_name,
    approval_year,
    naics_key,
    naics_sector_name,
    is_known_industry,
    total_approved_loan_amount,
    loan_count,
    approval_amount_coverage_count,
    average_loan_size,
    industry_approved_amount_share
from {{ ref('mart_lending_industry_state_period') }}
