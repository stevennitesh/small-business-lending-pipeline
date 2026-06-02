-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

select *
from {{ ref('mart_regional_business_health_annual_state') }}
where context_join_status != case
    when not has_lending_data then 'missing_lending'
    when not has_laus_data and not has_business_dynamics_data then 'missing_context'
    when not has_laus_data then 'missing_laus'
    when not has_business_dynamics_data then 'missing_business_dynamics'
    else 'complete_context'
end
