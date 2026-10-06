-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

with fact_totals as (
    select
        project_state_key as state_key,
        approval_year,
        sum(gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count,
        count(jobs_supported) as jobs_supported_coverage_count,
        sum(coalesce(jobs_supported, 0)) as total_jobs_supported
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null
      and approval_year is not null
    group by 1, 2
)

select coalesce(fact_totals.state_key, jobs.state_key) as state_key
from fact_totals
full outer join {{ ref('mart_lending_jobs_impact_state_period') }} as jobs
    using (state_key, approval_year)
where abs(coalesce(fact_totals.total_approved_loan_amount, 0) - coalesce(jobs.total_approved_loan_amount, 0)) > 0.01
   or coalesce(fact_totals.loan_count, 0) != coalesce(jobs.loan_count, 0)
   or coalesce(fact_totals.jobs_supported_coverage_count, 0) != coalesce(jobs.jobs_supported_coverage_count, 0)
   or coalesce(fact_totals.total_jobs_supported, 0) != coalesce(jobs.total_jobs_supported, 0)
