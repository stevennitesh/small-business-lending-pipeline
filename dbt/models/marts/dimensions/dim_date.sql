with source_dates as (
    select approval_date as date_day
    from {{ ref('stg_sba_loans') }}
    where approval_date is not null

    union all

    select observed_month as date_day
    from {{ ref('stg_bls_laus_state_month') }}
    where observed_month is not null

    union all

    select make_date(year, 1, 1) as date_day
    from {{ ref('stg_census_bds_state_year') }}
    where year is not null
),

bounds as (
    select
        coalesce(min(date_day), current_date)::date as start_date,
        coalesce(max(date_day), current_date)::date as end_date
    from source_dates
)

select
    try_cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day::date as date_day,
    extract(year from date_day)::integer as year,
    extract(quarter from date_day)::integer as quarter,
    extract(month from date_day)::integer as month,
    extract(day from date_day)::integer as day_of_month,
    strftime(date_day, '%Y-%m') as year_month
from generate_series(
    (select start_date from bounds),
    (select end_date from bounds),
    interval 1 day
) as spine(date_day)
