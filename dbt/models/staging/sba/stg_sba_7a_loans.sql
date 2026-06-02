-- Staging model: standardize raw fields after restricting records to latest validated manifests.

{% set raw_sba_7a_foia = source('raw', 'raw_sba_7a_foia') %}

with latest_successful_manifests as (
    select
        pipeline_run_id,
        resource_name,
        raw_uri
    from {{ ref('stg_ingestion_manifest') }}
    where source_system = 'sba'
      and dataset_name = '7a_504_foia'
      and resource_name like 'sba_7a_%'
      and validation_status = 'passed'
      and is_latest_successful_snapshot
),

raw_rows as (
    select
        raw.program,
        raw.locationid,
        raw.borrname,
        raw.borrcity,
        raw.borrstate,
        raw.borrzip,
        raw.bankname,
        raw.bankfdicnumber,
        raw.bankncuanumber,
        raw.bankstate,
        raw.projectcounty,
        raw.projectstate,
        raw.grossapproval,
        raw.sbaguaranteedapproval,
        raw.approvaldate,
        raw.approvalfy,
        raw.firstdisbursementdate,
        raw.processingmethod,
        raw.subprogram,
        raw.initialinterestrate,
        raw.fixedorvariableinterestind,
        raw.terminmonths,
        raw.naicscode,
        raw.naicsdescription,
        raw.franchisecode,
        raw.franchisename,
        raw.sbadistrictoffice,
        raw.congressionaldistrict,
        raw.businesstype,
        raw.businessage,
        raw.loanstatus,
        raw.paidinfulldate,
        raw.chargeoffdate,
        raw.grosschargeoffamount,
        raw.revolverstatus,
        raw.jobssupported,
        raw.collateralind,
        raw.soldsecmrktind,
        raw.pipeline_run_id,
        raw.source_system,
        raw.source_dataset,
        raw.source_resource_name,
        raw.ingestion_date,
        raw.raw_file_path,
        raw.sha256_checksum,
        raw.raw_uri as artifact_raw_uri,
        raw.storage_backend as artifact_storage_backend
    from {{ raw_sba_7a_foia }} as raw
),

source_rows as (
    select
        raw.program,
        raw.locationid,
        raw.borrname,
        raw.borrcity,
        raw.borrstate,
        raw.borrzip,
        raw.bankname,
        raw.bankfdicnumber,
        raw.bankncuanumber,
        raw.bankstate,
        raw.projectcounty,
        raw.projectstate,
        raw.grossapproval,
        raw.sbaguaranteedapproval,
        raw.approvaldate,
        raw.approvalfy,
        raw.firstdisbursementdate,
        raw.processingmethod,
        raw.subprogram,
        raw.initialinterestrate,
        raw.fixedorvariableinterestind,
        raw.terminmonths,
        raw.naicscode,
        raw.naicsdescription,
        raw.franchisecode,
        raw.franchisename,
        raw.sbadistrictoffice,
        raw.congressionaldistrict,
        raw.businesstype,
        raw.businessage,
        raw.loanstatus,
        raw.paidinfulldate,
        raw.chargeoffdate,
        raw.grosschargeoffamount,
        raw.revolverstatus,
        raw.jobssupported,
        raw.collateralind,
        raw.soldsecmrktind,
        raw.pipeline_run_id,
        raw.source_system,
        raw.source_dataset,
        raw.source_resource_name,
        raw.ingestion_date,
        raw.raw_file_path,
        raw.sha256_checksum,
        raw.artifact_raw_uri,
        raw.artifact_storage_backend,
        row_number() over (
            partition by raw.pipeline_run_id, raw.source_resource_name, raw.artifact_raw_uri
            order by raw.locationid, raw.approvaldate, raw.borrname, raw.grossapproval
        ) as raw_row_number
    from raw_rows as raw
    inner join latest_successful_manifests as manifest
        on raw.pipeline_run_id = manifest.pipeline_run_id
       and raw.source_resource_name = manifest.resource_name
       and raw.artifact_raw_uri = manifest.raw_uri
),

standardized as (
    select
        {{ generate_surrogate_key([
            "'7a'",
            "artifact_raw_uri",
            "raw_row_number",
            "locationid",
            "approvaldate",
            "grossapproval"
        ]) }} as loan_record_key,
        '7a' as loan_program,
        trim(cast(program as varchar)) as source_program,
        nullif(trim(cast(locationid as varchar)), '') as source_loan_id,
        nullif(trim(cast(borrname as varchar)), '') as borrower_name,
        nullif(trim(cast(borrcity as varchar)), '') as borrower_city,
        upper(nullif(trim(cast(borrstate as varchar)), '')) as borrower_state_abbr,
        lpad(cast(borrower_state.state_fips as varchar), 2, '0') as borrower_state_fips,
        case
            when nullif(trim(cast(borrstate as varchar)), '') is null then 'missing'
            when borrower_state.state_fips is null then 'unmapped'
            else 'mapped'
        end as borrower_state_match_status,
        nullif(trim(cast(borrzip as varchar)), '') as borrower_zip,
        {{ clean_lender_name('bankname') }} as lender_name,
        nullif(trim(cast(bankfdicnumber as varchar)), '') as lender_fdic_number,
        nullif(trim(cast(bankncuanumber as varchar)), '') as lender_ncua_number,
        cast(null as varchar) as cdc_name,
        cast(null as varchar) as cdc_state_abbr,
        upper(nullif(trim(cast(bankstate as varchar)), '')) as lender_state_abbr,
        cast(null as decimal(18, 2)) as third_party_dollars,
        nullif(trim(cast(projectcounty as varchar)), '') as project_county,
        upper(nullif(trim(cast(projectstate as varchar)), '')) as project_state_abbr,
        lpad(cast(project_state.state_fips as varchar), 2, '0') as project_state_fips,
        case
            when nullif(trim(cast(projectstate as varchar)), '') is null then 'missing'
            when project_state.state_fips is null then 'unmapped'
            else 'mapped'
        end as project_state_match_status,
        case
            when try_cast(replace(replace(cast(grossapproval as varchar), ',', ''), '$', '') as decimal(18, 2)) >= 0
                then try_cast(replace(replace(cast(grossapproval as varchar), ',', ''), '$', '') as decimal(18, 2))
            else null
        end as gross_approval_amount,
        try_cast(replace(replace(cast(sbaguaranteedapproval as varchar), ',', ''), '$', '') as decimal(18, 2)) as sba_guaranteed_approval_amount,
        {{ parse_mdy_date("nullif(trim(cast(approvaldate as varchar)), '')") }} as approval_date,
        try_cast(cast(approvalfy as varchar) as integer) as approval_fiscal_year,
        {{ parse_mdy_date("nullif(trim(cast(firstdisbursementdate as varchar)), '')") }} as first_disbursement_date,
        nullif(trim(cast(processingmethod as varchar)), '') as processing_method,
        nullif(trim(cast(subprogram as varchar)), '') as subprogram,
        try_cast(replace(cast(initialinterestrate as varchar), '%', '') as decimal(9, 4)) as initial_interest_rate,
        nullif(trim(cast(fixedorvariableinterestind as varchar)), '') as fixed_or_variable_interest_indicator,
        try_cast(cast(terminmonths as varchar) as integer) as term_months,
        nullif(trim(cast(naicscode as varchar)), '') as naics_code,
        nullif(trim(cast(naicsdescription as varchar)), '') as naics_description,
        nullif(trim(cast(franchisecode as varchar)), '') as franchise_code,
        nullif(trim(cast(franchisename as varchar)), '') as franchise_name,
        nullif(trim(cast(sbadistrictoffice as varchar)), '') as sba_district_office,
        nullif(trim(cast(congressionaldistrict as varchar)), '') as congressional_district,
        nullif(trim(cast(businesstype as varchar)), '') as business_type,
        nullif(trim(cast(businessage as varchar)), '') as business_age,
        nullif(trim(cast(loanstatus as varchar)), '') as loan_status,
        {{ parse_mdy_date("nullif(trim(cast(paidinfulldate as varchar)), '')") }} as paid_in_full_date,
        {{ parse_mdy_date("nullif(trim(cast(chargeoffdate as varchar)), '')") }} as chargeoff_date,
        try_cast(replace(replace(cast(grosschargeoffamount as varchar), ',', ''), '$', '') as decimal(18, 2)) as gross_chargeoff_amount,
        nullif(trim(cast(revolverstatus as varchar)), '') as revolver_status,
        try_cast(cast(jobssupported as varchar) as integer) as jobs_supported,
        nullif(trim(cast(collateralind as varchar)), '') as collateral_indicator,
        nullif(trim(cast(soldsecmrktind as varchar)), '') as sold_secondary_market_indicator,
        pipeline_run_id,
        source_system,
        source_dataset,
        source_resource_name,
        ingestion_date,
        artifact_storage_backend as storage_backend,
        artifact_raw_uri as raw_uri,
        raw_file_path,
        sha256_checksum,
        raw_row_number
    from source_rows
    left join {{ ref('ref_state') }} as borrower_state
        on upper(nullif(trim(cast(source_rows.borrstate as varchar)), '')) = borrower_state.state_abbr
    left join {{ ref('ref_state') }} as project_state
        on upper(nullif(trim(cast(source_rows.projectstate as varchar)), '')) = project_state.state_abbr
)

select
    loan_record_key,
    loan_program,
    source_program,
    source_loan_id,
    borrower_name,
    borrower_city,
    borrower_state_abbr,
    borrower_state_fips,
    borrower_state_match_status,
    borrower_zip,
    lender_name,
    lender_fdic_number,
    lender_ncua_number,
    cdc_name,
    cdc_state_abbr,
    lender_state_abbr,
    third_party_dollars,
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
    naics_description,
    franchise_code,
    franchise_name,
    sba_district_office,
    congressional_district,
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
    pipeline_run_id,
    source_system,
    source_dataset,
    source_resource_name,
    ingestion_date,
    storage_backend,
    raw_uri,
    raw_file_path,
    sha256_checksum,
    raw_row_number
from standardized
