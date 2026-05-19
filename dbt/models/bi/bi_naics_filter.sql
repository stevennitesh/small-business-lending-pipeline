select
    naics_key,
    naics_sector_code,
    naics_sector_name,
    naics_description,
    is_valid_current_code,
    is_unknown
from {{ ref('dim_naics') }}
