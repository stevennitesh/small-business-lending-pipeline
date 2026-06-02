-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

select *
from {{ ref('bi_lender_mix') }}
where lender_key = 'UNKNOWN'
   or lower(lender_name) like 'unknown%'
