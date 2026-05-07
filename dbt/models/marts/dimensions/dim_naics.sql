select
    'UNKNOWN' as naics_key,
    'UNKNOWN' as naics_sector_code,
    'Unknown NAICS sector' as naics_sector_name,
    'Unknown or missing NAICS sector' as naics_description,
    false as is_valid_current_code,
    true as is_unknown

union all

select
    naics_sector_code as naics_key,
    naics_sector_code,
    naics_sector_name,
    naics_description,
    try_cast(is_valid_current_code as boolean) as is_valid_current_code,
    false as is_unknown
from {{ ref('ref_naics') }}
