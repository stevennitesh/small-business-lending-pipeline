-- Context mart: prepare regional economic indicators at the state/time grain used beside lending KPIs.

with state_years as (
    -- Build the union grain first so context gaps are visible instead of
    -- silently dropping state/year rows with partial source coverage.
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
        lending.approval_amount_coverage_count,
        lending.average_loan_size,
        laus.annual_average_unemployment_rate,
        laus.unemployment_rate_yoy_change_pp,
        laus.observed_month_count,
        laus.observed_expected_month_count,
        laus.unexpected_month_count,
        laus.expected_month_count,
        laus.publisher_omitted_month_count,
        laus.missing_month_count,
        laus.is_year_to_date,
        laus.is_comparable_annual,
        laus.annual_coverage_status,
        lending.is_full_calendar_year,
        bds.bds_reference_date,
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
    joined.approval_amount_coverage_count,
    joined.average_loan_size,
    joined.annual_average_unemployment_rate,
    joined.unemployment_rate_yoy_change_pp,
    joined.observed_month_count,
    joined.observed_expected_month_count,
    joined.unexpected_month_count,
    joined.expected_month_count,
    joined.publisher_omitted_month_count,
    joined.missing_month_count,
    joined.is_year_to_date,
    joined.is_comparable_annual,
    joined.annual_coverage_status,
    joined.is_full_calendar_year,
    coalesce(joined.is_full_calendar_year and joined.is_comparable_annual
        and joined.has_business_dynamics_data and joined.establishment_count > 0, false) as is_comparable_context,
    coalesce(joined.has_lending_data and joined.establishment_count > 0, false) as has_matched_establishment_population,
    joined.bds_reference_date,
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
    -- BI can filter on this status to show only complete context or diagnose
    -- which upstream source is missing for a state/year.
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
