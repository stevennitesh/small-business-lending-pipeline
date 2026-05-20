with status_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        fact.loan_status_group,
        fact.loan_status_group_label,
        fact.loan_status_sort_order,
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
    group by 1, 2, 3, 4, 5
)

select
    status_period.state_key,
    state.state_name,
    status_period.approval_year,
    status_period.loan_status_group,
    status_period.loan_status_group_label,
    status_period.loan_status_sort_order,
    status_period.total_approved_loan_amount,
    status_period.loan_count,
    {{ safe_divide(
        'status_period.total_approved_loan_amount',
        'status_period.loan_count'
    ) }} as average_loan_size,
    status_period.gross_chargeoff_amount,
    status_period.charged_off_loan_count,
    {{ safe_divide(
        'status_period.total_approved_loan_amount',
        'performance.total_approved_loan_amount'
    ) }} as status_group_approved_amount_share,
    {{ safe_divide(
        'status_period.loan_count',
        'performance.loan_count'
    ) }} as status_group_loan_count_share
from status_period
inner join {{ ref('mart_lending_performance_state_period') }} as performance
    on status_period.state_key = performance.state_key
   and status_period.approval_year = performance.approval_year
left join {{ ref('dim_state') }} as state
    on status_period.state_key = state.state_key
