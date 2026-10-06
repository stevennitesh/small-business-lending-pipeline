-- Lending mart: aggregate SBA loan facts to the dashboard grain while keeping KPI math in dbt.

with eligible_loans as (
    select
        project_state_key,
        approval_year,
        gross_approval_amount,
        term_months,
        initial_interest_rate,
        fixed_or_variable_interest_indicator,
        loan_program_key,
        sba_guaranteed_approval_amount,
        third_party_dollars,
        loan_program_key = '7a' and sba_guaranteed_approval_amount is not null
            and gross_approval_amount is not null as has_paired_7a_guarantee,
        loan_program_key = '504' and third_party_dollars is not null
            and gross_approval_amount is not null as has_paired_504_financing
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null and approval_year is not null
),
state_period as (
    select
        fact.project_state_key as state_key,
        fact.approval_year,
        sum(fact.gross_approval_amount) as total_approved_loan_amount,
        count(fact.gross_approval_amount) as approval_amount_coverage_count,
        count(*) as loan_count,
        count(fact.term_months) as term_coverage_count,
        avg(fact.term_months) as average_term_months,
        sum(fact.term_months) as total_term_months,
        count(fact.initial_interest_rate) as initial_interest_rate_coverage_count,
        avg(fact.initial_interest_rate / 100) as average_initial_interest_rate,
        sum(fact.initial_interest_rate / 100) as total_initial_interest_rate,
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
        sum(case when upper(trim(fact.fixed_or_variable_interest_indicator)) in ('F', 'FIXED', 'V', 'VARIABLE') then 1 else 0 end) as interest_type_coverage_count,
        sum(
            case
                when fact.loan_program_key = '7a' then fact.gross_approval_amount
                else 0
            end
        ) as seven_a_approved_loan_amount,
        sum(case when fact.loan_program_key = '7a' then coalesce(fact.sba_guaranteed_approval_amount, 0) else 0 end) as sba_guaranteed_approval_amount,
        sum(case when fact.loan_program_key = '7a' then 1 else 0 end) as program_7a_loan_count,
        sum(case when fact.has_paired_7a_guarantee then 1 else 0 end) as paired_7a_coverage_count,
        sum(case when fact.has_paired_7a_guarantee then fact.sba_guaranteed_approval_amount else 0 end) as paired_7a_guaranteed_amount,
        sum(case when fact.has_paired_7a_guarantee then fact.gross_approval_amount else 0 end) as paired_7a_approval_amount,
        sum(coalesce(fact.third_party_dollars, 0)) as third_party_dollars,
        sum(case when fact.loan_program_key = '504' then 1 else 0 end) as program_504_loan_count,
        sum(case when fact.has_paired_504_financing then 1 else 0 end) as paired_504_coverage_count,
        sum(case when fact.has_paired_504_financing then fact.third_party_dollars else 0 end) as paired_504_third_party_dollars,
        sum(case when fact.has_paired_504_financing then fact.gross_approval_amount else 0 end) as paired_504_approval_amount
    from eligible_loans as fact
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
    state_period.term_coverage_count,
    {{ safe_divide(
        'state_period.term_coverage_count',
        'state_period.loan_count'
    ) }} as term_coverage_rate,
    state_period.average_term_months,
    state_period.total_term_months,
    state_period.initial_interest_rate_coverage_count,
    {{ safe_divide(
        'state_period.initial_interest_rate_coverage_count',
        'state_period.loan_count'
    ) }} as initial_interest_rate_coverage_rate,
    state_period.average_initial_interest_rate,
    state_period.total_initial_interest_rate,
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
    state_period.program_7a_loan_count,
    state_period.paired_7a_coverage_count,
    state_period.paired_7a_guaranteed_amount,
    state_period.paired_7a_approval_amount,
    {{ safe_divide('state_period.paired_7a_coverage_count', 'state_period.program_7a_loan_count') }} as paired_7a_coverage_rate,
    {{ safe_divide(
        'state_period.paired_7a_guaranteed_amount',
        'state_period.paired_7a_approval_amount'
    ) }} as seven_a_sba_guarantee_rate,
    state_period.program_504_loan_count,
    state_period.paired_504_coverage_count,
    state_period.paired_504_third_party_dollars,
    state_period.paired_504_approval_amount,
    {{ safe_divide('state_period.paired_504_coverage_count', 'state_period.program_504_loan_count') }} as paired_504_coverage_rate,
    {{ safe_divide('state_period.paired_504_third_party_dollars', 'state_period.paired_504_approval_amount') }} as known_504_third_party_to_sba_amount_rate,
    -- Deprecated mixed-program ratio retained for old exports; new visuals use the paired 504 measure.
    state_period.third_party_dollars,
    {{ safe_divide(
        'state_period.third_party_dollars',
        'state_period.total_approved_loan_amount'
    ) }} as third_party_to_approved_amount_rate
from state_period
left join {{ ref('dim_state') }} as state
    on state_period.state_key = state.state_key
