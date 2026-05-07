with loans as (
    select
        *,
        case
            when naics_code is null then 'UNKNOWN'
            when substr(naics_code, 1, 2) in ('31', '32', '33') then '31-33'
            when substr(naics_code, 1, 2) in ('44', '45') then '44-45'
            when substr(naics_code, 1, 2) in ('48', '49') then '48-49'
            else substr(naics_code, 1, 2)
        end as naics_sector_key
    from {{ ref('stg_sba_loans') }}
)

select
    loan_record_key as sba_loan_fact_key,
    loan_record_key,
    loans.loan_program as loan_program_key,
    coalesce(lender.lender_key, 'UNKNOWN') as lender_key,
    coalesce(naics.naics_key, 'UNKNOWN') as naics_key,
    project_state_fips as project_state_key,
    borrower_state_fips as borrower_state_key,
    source_file.source_file_key,
    try_cast(strftime(approval_date, '%Y%m%d') as integer) as approval_date_key,
    approval_date,
    approval_fiscal_year,
    first_disbursement_date,
    source_loan_id,
    borrower_name,
    borrower_city,
    borrower_state_abbr,
    borrower_state_match_status,
    project_county,
    project_state_abbr,
    project_state_match_status,
    gross_approval_amount,
    sba_guaranteed_approval_amount,
    gross_chargeoff_amount,
    jobs_supported,
    term_months,
    initial_interest_rate,
    processing_method,
    subprogram,
    loan_status,
    loans.pipeline_run_id,
    loans.source_resource_name,
    loans.raw_file_path,
    loans.sha256_checksum
from loans
left join {{ ref('dim_lender') }} as lender
    on loans.lender_name = lender.lender_name
left join {{ ref('dim_naics') }} as naics
    on loans.naics_sector_key = naics.naics_key
left join {{ ref('dim_source_file') }} as source_file
    on loans.raw_file_path = source_file.raw_file_path
