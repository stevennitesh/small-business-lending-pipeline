-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

select
    'bi_regional_business_health' as model_name,
    state_key,
    year,
    annual_average_unemployment_rate,
    establishment_entry_rate,
    establishment_exit_rate,
    unemployment_rate_yoy_change_pct
from {{ ref('bi_regional_business_health') }}
where annual_average_unemployment_rate < 0
   or annual_average_unemployment_rate > 1
   or establishment_entry_rate < 0
   or establishment_entry_rate > 1
   or establishment_exit_rate < 0
   or establishment_exit_rate > 1
   or abs(unemployment_rate_yoy_change_pct) > 1
