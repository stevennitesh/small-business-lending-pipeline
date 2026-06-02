-- Context mart: prepare regional economic indicators at the state/time grain used beside lending KPIs.

with monthly as (
    select
        state_key,
        observed_month,
        year,
        unemployment_rate,
        lag(unemployment_rate, 12) over (
            partition by state_key
            order by observed_month
        ) as prior_year_unemployment_rate
    from {{ ref('fact_laus_state_month') }}
)

select
    monthly.state_key,
    state.state_name,
    monthly.observed_month,
    extract(year from monthly.observed_month)::integer as observed_year,
    extract(month from monthly.observed_month)::integer as observed_month_number,
    monthly.unemployment_rate,
    monthly.unemployment_rate - monthly.prior_year_unemployment_rate as unemployment_rate_yoy_change_pp
from monthly
left join {{ ref('dim_state') }} as state
    on monthly.state_key = state.state_key
