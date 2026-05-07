select
    state_fips as state_key,
    state_fips,
    state_abbr,
    state_name,
    census_region,
    census_division,
    try_cast(is_state as boolean) as is_state,
    try_cast(is_dc as boolean) as is_dc
from {{ ref('ref_state') }}
