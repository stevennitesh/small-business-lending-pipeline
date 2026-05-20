with state_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count,
        count(fact.term_months) as term_coverage_count,
        avg(fact.term_months) as average_term_months,
        count(fact.initial_interest_rate) as initial_interest_rate_coverage_count,
        avg(fact.initial_interest_rate / 100) as average_initial_interest_rate,
        sum(
            case
                when upper(trim(fact.fixed_or_variable_interest_indicator)) in ('F', 'FIXED') then 1
                else 0
            end
        ) as fixed_interest_loan_count,
        sum(
            case
                when upper(trim(fact.fixed_or_variable_interest_indicator)) in ('V', 'VARIABLE') then 1
                else 0
            end
        ) as variable_interest_loan_count,
        count(fact.fixed_or_variable_interest_indicator) as interest_type_coverage_count,
        sum(
            case
                when fact.loan_program_key = '7a' then fact.gross_approval_amount
                else 0
            end
        ) as seven_a_approved_loan_amount,
        sum(coalesce(fact.sba_guaranteed_approval_amount, 0)) as sba_guaranteed_approval_amount,
        sum(coalesce(fact.third_party_dollars, 0)) as third_party_dollars
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
    {{ safe_divide(
        'state_period.total_approved_loan_amount',
        'state_period.loan_count'
    ) }} as average_loan_size,
    state_period.term_coverage_count,
    {{ safe_divide(
        'state_period.term_coverage_count',
        'state_period.loan_count'
    ) }} as term_coverage_rate,
    state_period.average_term_months,
    state_period.initial_interest_rate_coverage_count,
    {{ safe_divide(
        'state_period.initial_interest_rate_coverage_count',
        'state_period.loan_count'
    ) }} as initial_interest_rate_coverage_rate,
    state_period.average_initial_interest_rate,
    state_period.interest_type_coverage_count,
    state_period.fixed_interest_loan_count,
    state_period.variable_interest_loan_count,
    {{ safe_divide(
        'state_period.fixed_interest_loan_count',
        'state_period.interest_type_coverage_count'
    ) }} as fixed_interest_loan_share,
    {{ safe_divide(
        'state_period.variable_interest_loan_count',
        'state_period.interest_type_coverage_count'
    ) }} as variable_interest_loan_share,
    state_period.seven_a_approved_loan_amount,
    state_period.sba_guaranteed_approval_amount,
    {{ safe_divide(
        'state_period.sba_guaranteed_approval_amount',
        'state_period.seven_a_approved_loan_amount'
    ) }} as seven_a_sba_guarantee_rate,
    state_period.third_party_dollars,
    {{ safe_divide(
        'state_period.third_party_dollars',
        'state_period.total_approved_loan_amount'
    ) }} as third_party_to_approved_amount_rate
from state_period
left join {{ ref('dim_state') }} as state
    on state_period.state_key = state.state_key
