-- Calendar approvals; full-year evidence comes from policy, not sparse record bounds.
{% set policy = var('reporting_policy') %}
with annual as (
    select
        project_state_key as state_key,
        approval_year,
        sum(gross_approval_amount) as total_approved_loan_amount,
        count(gross_approval_amount) as approval_amount_coverage_count,
        count(*) as loan_count,
        min(approval_date) as first_observed_approval_date,
        max(approval_date) as last_observed_approval_date
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null and approval_year is not null
    group by 1, 2
),
covered as (
    select
        state_key, approval_year, total_approved_loan_amount, loan_count, approval_amount_coverage_count,
        first_observed_approval_date, last_observed_approval_date,
        cast('{{ policy.sba_calendar_start }}' as date) as source_calendar_start,
        cast('{{ policy.sba_calendar_end }}' as date) as source_calendar_end,
        cast('{{ policy.evidence_as_of }}' as date) as coverage_evidence_as_of,
        cast(cast(approval_year as varchar) || '-01-01' as date) >= cast('{{ policy.sba_calendar_start }}' as date)
        and cast(cast(approval_year as varchar) || '-12-31' as date) <= cast('{{ policy.sba_calendar_end }}' as date)
        as is_full_calendar_year
    from annual
),
compared as (
    select
        state_key, approval_year, total_approved_loan_amount, loan_count, approval_amount_coverage_count,
        first_observed_approval_date, last_observed_approval_date,
        source_calendar_start, source_calendar_end, coverage_evidence_as_of,
        is_full_calendar_year,
        lag(approval_year) over (partition by state_key order by approval_year) as prior_approval_year,
        lag(is_full_calendar_year) over (partition by state_key order by approval_year) as prior_is_full_year,
        lag(total_approved_loan_amount) over (partition by state_key order by approval_year) as prior_amount,
        lag(loan_count) over (partition by state_key order by approval_year) as prior_count
    from covered
)
select
    compared.state_key, state.state_name, approval_year,
    total_approved_loan_amount, loan_count, approval_amount_coverage_count,
    {{ safe_divide('total_approved_loan_amount', 'approval_amount_coverage_count') }} as average_loan_size,
    first_observed_approval_date, last_observed_approval_date,
    source_calendar_start, source_calendar_end, coverage_evidence_as_of,
    is_full_calendar_year,
    case when is_full_calendar_year then 'full_year'
         when approval_year between extract(year from source_calendar_start) and extract(year from source_calendar_end)
         then 'partial_year' else 'outside_coverage_evidence' end as calendar_period_status,
    is_full_calendar_year and coalesce(prior_is_full_year, false)
        and prior_approval_year = approval_year - 1 as is_comparable_yoy,
    case when is_full_calendar_year and prior_is_full_year and prior_approval_year = approval_year - 1
         then prior_amount end as comparable_prior_year_amount,
    case when is_full_calendar_year and prior_is_full_year and prior_approval_year = approval_year - 1
         then {{ safe_divide('total_approved_loan_amount - prior_amount', 'prior_amount') }} end as approved_loan_amount_yoy_growth_pct,
    case when is_full_calendar_year and prior_is_full_year and prior_approval_year = approval_year - 1
         then {{ safe_divide('loan_count - prior_count', 'prior_count') }} end as loan_count_yoy_growth_pct
from compared
left join {{ ref('dim_state') }} as state on compared.state_key = state.state_key
