-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    loan_program_key,
    loan_program,
    loan_program_name,
    approval_amount_basis,
    reporting_lender_role
from {{ ref('dim_loan_program') }}
