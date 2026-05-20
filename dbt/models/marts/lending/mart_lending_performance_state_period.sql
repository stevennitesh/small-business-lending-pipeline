with state_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count,
        sum(coalesce(fact.gross_chargeoff_amount, 0)) as gross_chargeoff_amount,
        sum(
            case
                when fact.is_credit_loss_status then 1
                else 0
            end
        ) as charged_off_loan_count
    from {{ ref('fact_sba_loans') }} as fact
    where fact.project_state_key is not null
      and fact.approval_year is not null
    group by 1, 2
)

select
    state_period.state_key,
    state.state_name,
    state_period.approval_year,
    state_period.total_approved_loan_amount,
    state_period.loan_count,
    {{ safe_divide(
        'state_period.total_approved_loan_amount',
        'state_period.loan_count'
    ) }} as average_loan_size,
    state_period.gross_chargeoff_amount,
    state_period.charged_off_loan_count,
    {{ safe_divide(
        'state_period.gross_chargeoff_amount',
        'state_period.total_approved_loan_amount'
    ) }} as chargeoff_amount_rate,
    {{ safe_divide(
        'state_period.charged_off_loan_count',
        'state_period.loan_count'
    ) }} as charged_off_loan_count_rate
from state_period
left join {{ ref('dim_state') }} as state
    on state_period.state_key = state.state_key
