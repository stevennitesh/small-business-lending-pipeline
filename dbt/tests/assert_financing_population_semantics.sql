-- Paired financing is program-specific and cannot exceed eligible record coverage.
{{ config(tags=['critical']) }}
select state_key, approval_year
from {{ ref('mart_lending_terms_pricing_state_period') }}
where paired_504_coverage_count > program_504_loan_count
   or paired_7a_coverage_count > program_7a_loan_count
   or program_504_loan_count + program_7a_loan_count != loan_count
   or approval_amount_coverage_count > loan_count
   or paired_504_coverage_count > approval_amount_coverage_count
   or paired_7a_coverage_count > approval_amount_coverage_count
   or (paired_504_coverage_count = 0 and
       (paired_504_third_party_dollars != 0 or paired_504_approval_amount != 0))
   or (paired_7a_coverage_count = 0 and
       (paired_7a_guaranteed_amount != 0 or paired_7a_approval_amount != 0))
   or fixed_interest_loan_count + variable_interest_loan_count != interest_type_coverage_count
