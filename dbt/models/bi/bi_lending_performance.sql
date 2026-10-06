-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_name,
    approval_year,
    total_approved_loan_amount,
    loan_count,
    approval_amount_coverage_count,
    average_loan_size,
    gross_chargeoff_amount,
    charged_off_loan_count,
    chargeoff_amount_rate,
    charged_off_loan_count_rate
from {{ ref('mart_lending_performance_state_period') }}
