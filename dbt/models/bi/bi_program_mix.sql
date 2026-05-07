select
    state_key,
    state_name,
    approval_year,
    loan_program_key,
    loan_program_name,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    program_approved_amount_share
from {{ ref('mart_lending_program_state_period') }}
