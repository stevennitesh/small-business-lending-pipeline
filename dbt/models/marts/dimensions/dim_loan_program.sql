-- Dimension model: provide stable keys and labels for marts, BI filters, and reconciliation tests.

select
    '7a' as loan_program_key,
    '7a' as loan_program,
    'SBA 7(a)' as loan_program_name,
    'Whole 7(a) loan amount' as approval_amount_basis,
    'Currently assigned bank' as reporting_lender_role

union all

select
    '504' as loan_program_key,
    '504' as loan_program,
    'SBA 504' as loan_program_name,
    'SBA/CDC portion of 504 financing' as approval_amount_basis,
    'Reported third-party lender' as reporting_lender_role
