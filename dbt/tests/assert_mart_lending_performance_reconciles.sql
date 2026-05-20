with fact_totals as (
    select
        project_state_key as state_key,
        approval_year,
        sum(gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count,
        sum(coalesce(gross_chargeoff_amount, 0)) as gross_chargeoff_amount,
        sum(
            case
                when is_credit_loss_status then 1
                else 0
            end
        ) as charged_off_loan_count
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null
      and approval_year is not null
    group by 1, 2
)

select coalesce(fact_totals.state_key, performance.state_key) as state_key
from fact_totals
full outer join {{ ref('mart_lending_performance_state_period') }} as performance
    using (state_key, approval_year)
where abs(coalesce(fact_totals.total_approved_loan_amount, 0) - coalesce(performance.total_approved_loan_amount, 0)) > 0.01
   or coalesce(fact_totals.loan_count, 0) != coalesce(performance.loan_count, 0)
   or abs(coalesce(fact_totals.gross_chargeoff_amount, 0) - coalesce(performance.gross_chargeoff_amount, 0)) > 0.01
   or coalesce(fact_totals.charged_off_loan_count, 0) != coalesce(performance.charged_off_loan_count, 0)
