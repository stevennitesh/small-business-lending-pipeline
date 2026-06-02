-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

with ranked_lenders as (
    select
        state_key,
        approval_year,
        lender_key,
        total_approved_loan_amount,
        lender_rank,
        lag(total_approved_loan_amount) over (
            partition by state_key, approval_year
            order by lender_rank
        ) as previous_approved_loan_amount,
        lag(lender_key) over (
            partition by state_key, approval_year
            order by lender_rank
        ) as previous_lender_key
    from {{ ref('mart_lending_lender_state_period') }}
),

expected_concentration as (
    select
        state_key,
        approval_year,
        sum(case when lender_rank = 1 then total_approved_loan_amount else 0 end) as expected_top_1_approved_loan_amount,
        sum(case when lender_rank <= 5 then total_approved_loan_amount else 0 end) as expected_top_5_approved_loan_amount,
        sum(total_approved_loan_amount) as expected_total_approved_loan_amount
    from {{ ref('mart_lending_lender_state_period') }}
    group by 1, 2
),

ordering_failures as (
    select *
    from ranked_lenders
    where lender_rank < 1
       or previous_approved_loan_amount < total_approved_loan_amount
       or (
           previous_approved_loan_amount = total_approved_loan_amount
           and previous_lender_key > lender_key
       )
),

concentration_failures as (
    select
        concentration.state_key,
        concentration.approval_year,
        concentration.top_1_approved_loan_amount,
        expected_concentration.expected_top_1_approved_loan_amount,
        concentration.top_5_approved_loan_amount,
        expected_concentration.expected_top_5_approved_loan_amount,
        concentration.total_approved_loan_amount,
        expected_concentration.expected_total_approved_loan_amount
    from {{ ref('mart_lending_concentration_state_period') }} as concentration
    inner join expected_concentration
        on concentration.state_key = expected_concentration.state_key
       and concentration.approval_year = expected_concentration.approval_year
    where abs(
        concentration.top_1_approved_loan_amount
        - expected_concentration.expected_top_1_approved_loan_amount
    ) > 0.01
       or abs(
        concentration.top_5_approved_loan_amount
        - expected_concentration.expected_top_5_approved_loan_amount
    ) > 0.01
       or abs(
           concentration.total_approved_loan_amount
           - expected_concentration.expected_total_approved_loan_amount
       ) > 0.01
       or concentration.top_1_approved_loan_amount > concentration.top_5_approved_loan_amount
)

select
    'ordering' as failure_type,
    state_key,
    approval_year,
    lender_key,
    total_approved_loan_amount,
    lender_rank,
    previous_approved_loan_amount,
    previous_lender_key
from ordering_failures

union all

select
    'concentration' as failure_type,
    state_key,
    approval_year,
    cast(null as varchar) as lender_key,
    top_5_approved_loan_amount as total_approved_loan_amount,
    cast(null as integer) as lender_rank,
    expected_top_5_approved_loan_amount as previous_approved_loan_amount,
    cast(null as varchar) as previous_lender_key
from concentration_failures
