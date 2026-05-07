with mart_totals as (
    select
        state_key,
        approval_year,
        sum(total_approved_loan_amount) as total_approved_loan_amount,
        sum(loan_count) as loan_count
    from {{ ref('mart_lending_program_state_period') }}
    group by 1, 2
)

select annual.*
from {{ ref('mart_lending_annual_state') }} as annual
full outer join mart_totals using (state_key, approval_year)
where abs(coalesce(annual.total_approved_loan_amount, 0) - coalesce(mart_totals.total_approved_loan_amount, 0)) > 0.01
   or coalesce(annual.loan_count, 0) != coalesce(mart_totals.loan_count, 0)
