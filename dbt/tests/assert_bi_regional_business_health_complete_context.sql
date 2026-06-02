-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

select *
from {{ ref('bi_regional_business_health') }}
where context_join_status != 'complete_context'
   or annual_average_unemployment_rate is null
   or unemployment_rate_yoy_change_pct is null
   or establishment_count is null
   or establishment_entry_rate is null
   or establishment_exit_rate is null
   or loans_per_1000_establishments is null
   or approved_loan_dollars_per_establishment is null
