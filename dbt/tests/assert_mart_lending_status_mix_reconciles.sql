-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

with status_totals as (
    select
        state_key,
        approval_year,
        sum(total_approved_loan_amount) as total_approved_loan_amount,
        sum(loan_count) as loan_count,
        sum(gross_chargeoff_amount) as gross_chargeoff_amount,
        sum(charged_off_loan_count) as charged_off_loan_count,
        sum(status_group_approved_amount_share) as approved_amount_share_sum,
        sum(status_group_loan_count_share) as loan_count_share_sum
    from {{ ref('mart_lending_status_mix_state_period') }}
    group by 1, 2
)

select coalesce(performance.state_key, status_totals.state_key) as state_key
from {{ ref('mart_lending_performance_state_period') }} as performance
full outer join status_totals using (state_key, approval_year)
where abs(coalesce(performance.total_approved_loan_amount, 0) - coalesce(status_totals.total_approved_loan_amount, 0)) > 0.01
   or coalesce(performance.loan_count, 0) != coalesce(status_totals.loan_count, 0)
   or abs(coalesce(performance.gross_chargeoff_amount, 0) - coalesce(status_totals.gross_chargeoff_amount, 0)) > 0.01
   or coalesce(performance.charged_off_loan_count, 0) != coalesce(status_totals.charged_off_loan_count, 0)
   or (
       performance.total_approved_loan_amount > 0
       and abs(coalesce(status_totals.approved_amount_share_sum, 0) - 1) > 0.000001
   )
   or (
       performance.loan_count > 0
       and abs(coalesce(status_totals.loan_count_share_sum, 0) - 1) > 0.000001
   )
