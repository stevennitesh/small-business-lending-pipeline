-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

select 'dim_lender missing UNKNOWN row' as failure
where not exists (
    select 1
    from {{ ref('dim_lender') }}
    where lender_key = 'UNKNOWN'
      and is_unknown
)
