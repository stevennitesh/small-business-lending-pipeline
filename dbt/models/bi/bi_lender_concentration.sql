-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_name,
    approval_year,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    lender_count,
    top_1_approved_loan_amount,
    top_1_lender_share,
    top_5_approved_loan_amount,
    top_5_lender_share
from {{ ref('mart_lending_concentration_state_period') }}
