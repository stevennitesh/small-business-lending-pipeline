-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

with fact_totals as (
    select
        project_state_key as state_key,
        approval_year,
        sum(gross_approval_amount) as fact_total_approved_loan_amount,
        count(*) as fact_loan_count
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null
      and approval_year is not null
      and lender_key != 'UNKNOWN'
    group by 1, 2
),

mart_totals as (
    select
        state_key,
        approval_year,
        sum(total_approved_loan_amount) as mart_total_approved_loan_amount,
        sum(loan_count) as mart_loan_count
    from {{ ref('mart_lending_lender_state_period') }}
    group by 1, 2
)

select *
from fact_totals
full outer join mart_totals using (state_key, approval_year)
where abs(coalesce(fact_total_approved_loan_amount, 0) - coalesce(mart_total_approved_loan_amount, 0)) > 0.01
   or coalesce(fact_loan_count, 0) != coalesce(mart_loan_count, 0)
