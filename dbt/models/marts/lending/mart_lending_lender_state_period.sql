with lender_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        fact.lender_key,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count
    from {{ ref('fact_sba_loans') }} as fact
    where fact.project_state_key is not null
      and fact.approval_year is not null
      and fact.lender_key != 'UNKNOWN'
    group by 1, 2, 3
),

state_period as (
    select
        state_key,
        approval_year,
        sum(total_approved_loan_amount) as known_lender_approved_loan_amount
    from lender_period
    group by 1, 2
),

with_shares as (
    select
        lender_period.state_key,
        lender_period.approval_year,
        lender_period.lender_key,
        lender_period.total_approved_loan_amount,
        lender_period.loan_count,
        state_period.known_lender_approved_loan_amount as state_period_approved_loan_amount,
        {{ safe_divide(
            'lender_period.total_approved_loan_amount',
            'state_period.known_lender_approved_loan_amount'
        ) }} as lender_approved_amount_share,
        row_number() over (
            partition by lender_period.state_key, lender_period.approval_year
            order by lender_period.total_approved_loan_amount desc, lender_period.lender_key
        ) as lender_rank
    from lender_period
    inner join state_period
        on lender_period.state_key = state_period.state_key
       and lender_period.approval_year = state_period.approval_year
)

select
    with_shares.state_key,
    state.state_name,
    with_shares.approval_year,
    with_shares.lender_key,
    lender.lender_name,
    with_shares.total_approved_loan_amount,
    with_shares.loan_count,
    {{ safe_divide('with_shares.total_approved_loan_amount', 'with_shares.loan_count') }} as average_loan_size,
    with_shares.lender_approved_amount_share,
    with_shares.lender_rank
from with_shares
left join {{ ref('dim_state') }} as state
    on with_shares.state_key = state.state_key
left join {{ ref('dim_lender') }} as lender
    on with_shares.lender_key = lender.lender_key
