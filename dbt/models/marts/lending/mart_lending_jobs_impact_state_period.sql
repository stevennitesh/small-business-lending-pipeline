-- Lending mart: aggregate SBA loan facts to the dashboard grain while keeping KPI math in dbt.

with state_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(fact.gross_approval_amount) as approval_amount_coverage_count,
        count(*) as loan_count,
        count(fact.jobs_supported) as jobs_supported_coverage_count,
        sum(coalesce(fact.jobs_supported, 0)) as total_jobs_supported
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
    state_period.approval_amount_coverage_count,
    {{ safe_divide(
        'state_period.total_approved_loan_amount',
        'state_period.approval_amount_coverage_count'
    ) }} as average_loan_size,
    state_period.jobs_supported_coverage_count,
    {{ safe_divide(
        'state_period.jobs_supported_coverage_count',
        'state_period.loan_count'
    ) }} as jobs_supported_coverage_rate,
    state_period.total_jobs_supported,
    {{ safe_divide(
        'state_period.total_jobs_supported',
        'state_period.loan_count'
    ) }} as jobs_supported_per_loan,
    {{ safe_divide(
        'state_period.total_jobs_supported',
        'state_period.total_approved_loan_amount / 1000000'
    ) }} as jobs_supported_per_1m_approved,
    {{ safe_divide(
        'state_period.total_approved_loan_amount',
        'state_period.total_jobs_supported'
    ) }} as approved_loan_dollars_per_job_supported
from state_period
left join {{ ref('dim_state') }} as state
    on state_period.state_key = state.state_key
