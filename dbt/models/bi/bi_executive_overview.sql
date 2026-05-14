select
    state_key,
    state_name,
    approval_year as year,
    total_approved_loan_amount,
    loan_count,
    average_loan_size
from {{ ref('mart_lending_annual_state') }}
