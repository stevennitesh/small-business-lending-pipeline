with annual as (
    select
        project_state_key as state_key,
        coalesce(extract(year from approval_date)::integer, approval_fiscal_year) as approval_year,
        sum(gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null
      and coalesce(extract(year from approval_date)::integer, approval_fiscal_year) is not null
    group by 1, 2
),

with_context as (
    select
        annual.*,
        {{ safe_divide('total_approved_loan_amount', 'loan_count') }} as average_loan_size,
        lag(total_approved_loan_amount) over (
            partition by state_key
            order by approval_year
        ) as prior_year_approved_loan_amount,
        lag(loan_count) over (
            partition by state_key
            order by approval_year
        ) as prior_year_loan_count
    from annual
)

select
    with_context.state_key,
    state.state_name,
    approval_year,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    {{ safe_divide(
        'total_approved_loan_amount - prior_year_approved_loan_amount',
        'prior_year_approved_loan_amount'
    ) }} as approved_loan_amount_yoy_growth_pct,
    {{ safe_divide(
        'loan_count - prior_year_loan_count',
        'prior_year_loan_count'
    ) }} as loan_count_yoy_growth_pct
from with_context
left join {{ ref('dim_state') }} as state
    on with_context.state_key = state.state_key
