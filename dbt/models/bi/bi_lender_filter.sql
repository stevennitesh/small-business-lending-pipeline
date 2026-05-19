select
    lender_key,
    lender_name,
    is_unknown
from {{ ref('dim_lender') }}
where not is_unknown
