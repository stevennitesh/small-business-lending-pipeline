-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    lender_key,
    lender_name,
    is_unknown
from {{ ref('dim_lender') }}
where not is_unknown
