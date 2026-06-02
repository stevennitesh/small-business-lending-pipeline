-- Dimension model: provide stable keys and labels for marts, BI filters, and reconciliation tests.

select
    '7a' as loan_program_key,
    '7a' as loan_program,
    'SBA 7(a)' as loan_program_name

union all

select
    '504' as loan_program_key,
    '504' as loan_program,
    'SBA 504' as loan_program_name
