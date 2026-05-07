select *
from {{ ref('stg_sba_7a_loans') }}

union all

select *
from {{ ref('stg_sba_504_loans') }}
