-- Lending mart: aggregate SBA loan facts to the dashboard grain while keeping KPI math in dbt.

with industry_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        fact.naics_key,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(fact.gross_approval_amount) as approval_amount_coverage_count,
        count(*) as loan_count
    from {{ ref('fact_sba_loans') }} as fact
    where fact.project_state_key is not null
      and fact.approval_year is not null
    group by 1, 2, 3
)

select
    industry_period.state_key,
    state.state_name,
    industry_period.approval_year,
    industry_period.naics_key,
    naics.naics_sector_name,
    coalesce(naics.is_valid_current_code, false) as is_known_industry,
    industry_period.total_approved_loan_amount,
    industry_period.loan_count,
    industry_period.approval_amount_coverage_count,
    {{ safe_divide(
        'industry_period.total_approved_loan_amount',
        'industry_period.approval_amount_coverage_count'
    ) }} as average_loan_size,
    {{ safe_divide(
        'industry_period.total_approved_loan_amount',
        'annual.total_approved_loan_amount'
    ) }} as industry_approved_amount_share
from industry_period
inner join {{ ref('mart_lending_annual_state') }} as annual
    on industry_period.state_key = annual.state_key
   and industry_period.approval_year = annual.approval_year
left join {{ ref('dim_state') }} as state
    on industry_period.state_key = state.state_key
left join {{ ref('dim_naics') }} as naics
    on industry_period.naics_key = naics.naics_key
