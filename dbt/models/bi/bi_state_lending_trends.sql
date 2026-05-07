select
    state_key,
    state_name,
    approval_year,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    approved_loan_amount_yoy_growth_pct,
    loan_count_yoy_growth_pct
from {{ ref('mart_lending_annual_state') }}
