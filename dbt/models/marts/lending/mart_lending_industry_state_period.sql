with industry_period as (
    select
        fact.project_state_key as state_key,
        coalesce(extract(year from fact.approval_date)::integer, fact.approval_fiscal_year) as approval_year,
        fact.naics_key,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count
    from {{ ref('fact_sba_loans') }} as fact
    where fact.project_state_key is not null
      and coalesce(extract(year from fact.approval_date)::integer, fact.approval_fiscal_year) is not null
    group by 1, 2, 3
)

select
    industry_period.state_key,
    state.state_name,
    industry_period.approval_year,
    industry_period.naics_key,
    naics.naics_sector_name,
    industry_period.total_approved_loan_amount,
    industry_period.loan_count,
    {{ safe_divide(
        'industry_period.total_approved_loan_amount',
        'industry_period.loan_count'
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
