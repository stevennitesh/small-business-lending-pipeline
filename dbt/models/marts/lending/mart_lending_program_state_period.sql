with program_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        fact.loan_program_key,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count
    from {{ ref('fact_sba_loans') }} as fact
    where fact.project_state_key is not null
      and fact.approval_year is not null
    group by 1, 2, 3
)

select
    program_period.state_key,
    state.state_name,
    program_period.approval_year,
    program_period.loan_program_key,
    program.loan_program_name,
    program_period.total_approved_loan_amount,
    program_period.loan_count,
    {{ safe_divide(
        'program_period.total_approved_loan_amount',
        'program_period.loan_count'
    ) }} as average_loan_size,
    {{ safe_divide(
        'program_period.total_approved_loan_amount',
        'annual.total_approved_loan_amount'
    ) }} as program_approved_amount_share
from program_period
inner join {{ ref('mart_lending_annual_state') }} as annual
    on program_period.state_key = annual.state_key
   and program_period.approval_year = annual.approval_year
left join {{ ref('dim_state') }} as state
    on program_period.state_key = state.state_key
left join {{ ref('dim_loan_program') }} as program
    on program_period.loan_program_key = program.loan_program_key
