-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_name,
    approval_year,
    lender_key,
    lender_name,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    lender_approved_amount_share,
    lender_rank
from {{ ref('mart_lending_lender_state_period') }}
where lender_key != 'UNKNOWN'
