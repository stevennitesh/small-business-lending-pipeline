with annual as (
    select
        state_key,
        year,
        avg(unemployment_rate) as annual_average_unemployment_rate
    from {{ ref('fact_laus_state_month') }}
    group by 1, 2
),

with_context as (
    select
        annual.state_key,
        annual.year,
        annual.annual_average_unemployment_rate,
        lag(annual_average_unemployment_rate) over (
            partition by state_key
            order by year
        ) as prior_year_annual_average_unemployment_rate
    from annual
)

select
    with_context.state_key,
    state.state_name,
    with_context.year,
    with_context.annual_average_unemployment_rate,
    (
        with_context.annual_average_unemployment_rate
        - with_context.prior_year_annual_average_unemployment_rate
    ) as unemployment_rate_yoy_change_pp
from with_context
left join {{ ref('dim_state') }} as state
    on with_context.state_key = state.state_key
