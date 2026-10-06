-- Custom dbt data test: this query should return zero rows when the modeled contract holds.

with fact_totals as (
    select
        project_state_key as state_key,
        approval_year,
        sum(gross_approval_amount) as total_approved_loan_amount,
        count(*) as loan_count,
        count(term_months) as term_coverage_count,
        count(initial_interest_rate) as initial_interest_rate_coverage_count,
        sum(case when upper(trim(fixed_or_variable_interest_indicator)) in ('F', 'FIXED', 'V', 'VARIABLE') then 1 else 0 end) as interest_type_coverage_count,
        sum(
            case
                when loan_program_key = '7a' then gross_approval_amount
                else 0
            end
        ) as seven_a_approved_loan_amount,
        sum(case when loan_program_key = '7a' then coalesce(sba_guaranteed_approval_amount, 0) else 0 end) as sba_guaranteed_approval_amount,
        sum(coalesce(third_party_dollars, 0)) as third_party_dollars
    from {{ ref('fact_sba_loans') }}
    where project_state_key is not null
      and approval_year is not null
    group by 1, 2
)

select coalesce(fact_totals.state_key, terms.state_key) as state_key
from fact_totals
full outer join {{ ref('mart_lending_terms_pricing_state_period') }} as terms
    using (state_key, approval_year)
where abs(coalesce(fact_totals.total_approved_loan_amount, 0) - coalesce(terms.total_approved_loan_amount, 0)) > 0.01
   or coalesce(fact_totals.loan_count, 0) != coalesce(terms.loan_count, 0)
   or coalesce(fact_totals.term_coverage_count, 0) != coalesce(terms.term_coverage_count, 0)
   or coalesce(fact_totals.initial_interest_rate_coverage_count, 0) != coalesce(terms.initial_interest_rate_coverage_count, 0)
   or coalesce(fact_totals.interest_type_coverage_count, 0) != coalesce(terms.interest_type_coverage_count, 0)
   or abs(coalesce(fact_totals.seven_a_approved_loan_amount, 0) - coalesce(terms.seven_a_approved_loan_amount, 0)) > 0.01
   or abs(coalesce(fact_totals.sba_guaranteed_approval_amount, 0) - coalesce(terms.sba_guaranteed_approval_amount, 0)) > 0.01
   or abs(coalesce(fact_totals.third_party_dollars, 0) - coalesce(terms.third_party_dollars, 0)) > 0.01
