with state_years as (
    select state_key, approval_year as year
    from {{ ref('mart_lending_annual_state') }}

    union

    select state_key, year
    from {{ ref('mart_laus_annual_state') }}

    union

    select state_key, year
    from {{ ref('mart_business_dynamics_annual_state') }}
),

joined as (
    select
        state_years.state_key,
        state_years.year,
        lending.total_approved_loan_amount,
        lending.loan_count,
        lending.average_loan_size,
        laus.annual_average_unemployment_rate,
        laus.unemployment_rate_yoy_change_pp,
        bds.establishment_count,
        bds.establishment_entry_rate,
        bds.establishment_exit_rate,
        lending.state_key is not null as has_lending_data,
        laus.state_key is not null as has_laus_data,
        bds.state_key is not null as has_business_dynamics_data
    from state_years
    left join {{ ref('mart_lending_annual_state') }} as lending
        on state_years.state_key = lending.state_key
       and state_years.year = lending.approval_year
    left join {{ ref('mart_laus_annual_state') }} as laus
        on state_years.state_key = laus.state_key
       and state_years.year = laus.year
    left join {{ ref('mart_business_dynamics_annual_state') }} as bds
        on state_years.state_key = bds.state_key
       and state_years.year = bds.year
)

select
    joined.state_key,
    state.state_name,
    joined.year,
    joined.total_approved_loan_amount,
    joined.loan_count,
    joined.average_loan_size,
    joined.annual_average_unemployment_rate,
    joined.unemployment_rate_yoy_change_pp,
    joined.establishment_count,
    joined.establishment_entry_rate,
    joined.establishment_exit_rate,
    {{ safe_divide(
        'joined.loan_count * 1000.0',
        'joined.establishment_count'
    ) }} as loans_per_1000_establishments,
    {{ safe_divide(
        'joined.total_approved_loan_amount',
        'joined.establishment_count'
    ) }} as approved_loan_dollars_per_establishment,
    joined.has_lending_data,
    joined.has_laus_data,
    joined.has_business_dynamics_data,
    case
        when not joined.has_lending_data then 'missing_lending'
        when not joined.has_laus_data and not joined.has_business_dynamics_data then 'missing_context'
        when not joined.has_laus_data then 'missing_laus'
        when not joined.has_business_dynamics_data then 'missing_business_dynamics'
        else 'complete_context'
    end as context_join_status
from joined
left join {{ ref('dim_state') }} as state
    on joined.state_key = state.state_key
