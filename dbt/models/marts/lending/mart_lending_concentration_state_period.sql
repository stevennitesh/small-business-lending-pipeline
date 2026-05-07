with lender_period as (
    select *
    from {{ ref('mart_lending_lender_state_period') }}
),

concentration as (
    select
        state_key,
        approval_year,
        sum(case when lender_rank <= 5 then total_approved_loan_amount else 0 end) as top_5_approved_loan_amount,
        sum(total_approved_loan_amount) as total_approved_loan_amount,
        sum(loan_count) as loan_count,
        count(*) as lender_count
    from lender_period
    group by 1, 2
)

select
    concentration.state_key,
    state.state_name,
    concentration.approval_year,
    concentration.total_approved_loan_amount,
    concentration.loan_count,
    {{ safe_divide(
        'concentration.total_approved_loan_amount',
        'concentration.loan_count'
    ) }} as average_loan_size,
    concentration.lender_count,
    concentration.top_5_approved_loan_amount,
    {{ safe_divide(
        'concentration.top_5_approved_loan_amount',
        'concentration.total_approved_loan_amount'
    ) }} as top_5_lender_share
from concentration
left join {{ ref('dim_state') }} as state
    on concentration.state_key = state.state_key
