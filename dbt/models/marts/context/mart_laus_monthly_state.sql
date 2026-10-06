-- Context mart: prepare regional economic indicators at the state/time grain used beside lending KPIs.

with monthly as (
    select current.state_key, current.observed_month, current.year,
        current.unemployment_rate,
        prior.unemployment_rate as prior_year_unemployment_rate
    from {{ ref('fact_laus_state_month') }} as current
    left join {{ ref('fact_laus_state_month') }} as prior
        on current.state_key = prior.state_key
        and prior.year = current.year - 1
        and extract(month from current.observed_month) = extract(month from prior.observed_month)
)

select
    monthly.state_key,
    state.state_name,
    monthly.observed_month,
    extract(year from monthly.observed_month)::integer as observed_year,
    extract(month from monthly.observed_month)::integer as observed_month_number,
    monthly.unemployment_rate,
    (monthly.unemployment_rate - monthly.prior_year_unemployment_rate) * 100 as unemployment_rate_yoy_change_pp
from monthly
left join {{ ref('dim_state') }} as state
    on monthly.state_key = state.state_key
