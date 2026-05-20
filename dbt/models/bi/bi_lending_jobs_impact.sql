select
    state_key,
    state_name,
    approval_year,
    total_approved_loan_amount,
    loan_count,
    average_loan_size,
    jobs_supported_coverage_count,
    jobs_supported_coverage_rate,
    total_jobs_supported,
    jobs_supported_per_loan,
    jobs_supported_per_1m_approved,
    approved_loan_dollars_per_job_supported
from {{ ref('mart_lending_jobs_impact_state_period') }}
