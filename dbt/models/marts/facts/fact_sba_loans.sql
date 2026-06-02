-- Fact model: preserve latest validated source lineage while exposing the analytical grain for marts.

with loans as (
    select
        loan_record_key,
        loan_program,
        source_loan_id,
        borrower_name,
        borrower_city,
        borrower_state_abbr,
        borrower_state_fips,
        borrower_state_match_status,
        lender_name,
        project_county,
        project_state_abbr,
        project_state_fips,
        project_state_match_status,
        gross_approval_amount,
        sba_guaranteed_approval_amount,
        approval_date,
        approval_fiscal_year,
        first_disbursement_date,
        processing_method,
        subprogram,
        initial_interest_rate,
        fixed_or_variable_interest_indicator,
        term_months,
        naics_code,
        business_type,
        business_age,
        loan_status,
        paid_in_full_date,
        chargeoff_date,
        gross_chargeoff_amount,
        revolver_status,
        jobs_supported,
        collateral_indicator,
        sold_secondary_market_indicator,
        third_party_dollars,
        pipeline_run_id,
        source_resource_name,
        storage_backend,
        raw_uri,
        raw_file_path,
        sha256_checksum,
        -- Group SBA NAICS values to the sector keys used by the reference
        -- dimension; composite sectors stay compatible with Census labels.
        case
            when naics_code is null then 'UNKNOWN'
            when substr(naics_code, 1, 2) in ('31', '32', '33') then '31-33'
            when substr(naics_code, 1, 2) in ('44', '45') then '44-45'
            when substr(naics_code, 1, 2) in ('48', '49') then '48-49'
            when substr(naics_code, 1, 2) in (
                '11', '21', '22', '23', '42', '51', '52', '53', '54', '55',
                '56', '61', '62', '71', '72', '81', '92', '99'
            ) then substr(naics_code, 1, 2)
            else 'UNKNOWN'
        end as naics_key,
        coalesce(
            nullif(upper(trim(cast(loan_status as varchar))), ''),
            'UNKNOWN'
        ) as loan_status_key
    from {{ ref('stg_sba_loans') }}
)

select
    loan_record_key as sba_loan_fact_key,
    loan_record_key,
    loans.loan_program as loan_program_key,
    case
        when lender_name is null then 'UNKNOWN'
        else {{ generate_surrogate_key(["lender_name"]) }}
    end as lender_key,
    loans.naics_key,
    project_state_fips as project_state_key,
    borrower_state_fips as borrower_state_key,
    case
        when raw_uri is null then null
        else {{ generate_surrogate_key(["raw_uri"]) }}
    end as source_file_key,
    {{ date_key('approval_date') }} as approval_date_key,
    approval_date,
    coalesce(
        extract(year from approval_date)::integer,
        approval_fiscal_year
    ) as approval_year,
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
    loans.loan_status_key,
    -- Status grouping stays reference-driven so KPI categories can change
    -- without rewriting the fact grain or historical source columns.
    coalesce(status.loan_status_group, 'unmapped') as loan_status_group,
    coalesce(status.loan_status_group_label, 'Unmapped or unknown') as loan_status_group_label,
    coalesce(status.is_credit_loss_status, false) as is_credit_loss_status,
    status.status_sort_order as loan_status_sort_order,
    paid_in_full_date,
    chargeoff_date,
    fixed_or_variable_interest_indicator,
    third_party_dollars,
    business_type,
    business_age,
    revolver_status,
    collateral_indicator,
    sold_secondary_market_indicator,
    loans.pipeline_run_id,
    loans.source_resource_name,
    loans.storage_backend,
    loans.raw_uri,
    loans.raw_file_path,
    loans.sha256_checksum
from loans
left join {{ ref('ref_loan_status_group') }} as status
    on loans.loan_status_key = status.loan_status_key
