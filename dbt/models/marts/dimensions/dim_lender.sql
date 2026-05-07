select
    'UNKNOWN' as lender_key,
    'Unknown lender' as lender_name,
    true as is_unknown

union all

select
    {{ generate_surrogate_key(["lender_name"]) }} as lender_key,
    lender_name,
    false as is_unknown
from (
    select distinct lender_name
    from {{ ref('stg_sba_loans') }}
    where lender_name is not null
)
