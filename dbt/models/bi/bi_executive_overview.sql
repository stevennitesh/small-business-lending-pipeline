with lending as (
    select *
    from {{ ref('mart_lending_annual_state') }}
),

context as (
    select
        state_key,
        year,
        annual_average_unemployment_rate,
        establishment_count,
        loans_per_1000_establishments,
        approved_loan_dollars_per_establishment,
        context_join_status
    from {{ ref('mart_regional_business_health_annual_state') }}
)

select
    lending.state_key,
    lending.state_name,
    lending.approval_year as year,
    lending.total_approved_loan_amount,
    lending.loan_count,
    lending.average_loan_size,
    context.annual_average_unemployment_rate,
    context.establishment_count,
    context.loans_per_1000_establishments,
    context.approved_loan_dollars_per_establishment,
    coalesce(context.context_join_status, 'missing_context') as context_join_status
from lending
left join context
    on lending.state_key = context.state_key
   and lending.approval_year = context.year
