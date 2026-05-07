select
    state_key,
    state_name,
    year,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    annual_average_unemployment_rate,
    establishment_count,
    loans_per_1000_establishments,
    approved_loan_dollars_per_establishment,
    context_join_status
from {{ ref('mart_regional_business_health_annual_state') }}
