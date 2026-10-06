-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_name,
    approval_year,
    loan_status_group,
    loan_status_group_label,
    loan_status_sort_order,
    total_approved_loan_amount,
    loan_count,
    approval_amount_coverage_count,
    average_loan_size,
    gross_chargeoff_amount,
    charged_off_loan_count,
    status_group_approved_amount_share,
    status_group_loan_count_share
from {{ ref('mart_lending_status_mix_state_period') }}
