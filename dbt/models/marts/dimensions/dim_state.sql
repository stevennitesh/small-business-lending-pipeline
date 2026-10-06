-- Dimension model: provide stable keys and labels for marts, BI filters, and reconciliation tests.

select
    lpad(cast(state_fips as varchar), 2, '0') as state_key,
    lpad(cast(state_fips as varchar), 2, '0') as state_fips,
    state_abbr,
    state_name,
    census_region,
    census_division,
    try_cast(is_state as boolean) as is_state,
    try_cast(is_dc as boolean) as is_dc
from {{ ref('ref_state') }}
