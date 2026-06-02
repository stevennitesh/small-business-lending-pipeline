-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    state_key,
    state_fips,
    state_abbr,
    state_name,
    census_region,
    census_division
from {{ ref('dim_state') }}
where is_state or is_dc
