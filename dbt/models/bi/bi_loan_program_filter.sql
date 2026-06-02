-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    loan_program_key,
    loan_program,
    loan_program_name
from {{ ref('dim_loan_program') }}
