select
    state_key,
    state_name,
    year,
    total_approved_loan_amount,
    loan_count,
    annual_average_unemployment_rate,
    unemployment_rate_yoy_change_pp,
    establishment_count,
    establishment_entry_rate,
    establishment_exit_rate,
    loans_per_1000_establishments,
    approved_loan_dollars_per_establishment,
    has_lending_data,
    has_laus_data,
    has_business_dynamics_data,
    context_join_status
from {{ ref('mart_regional_business_health_annual_state') }}
