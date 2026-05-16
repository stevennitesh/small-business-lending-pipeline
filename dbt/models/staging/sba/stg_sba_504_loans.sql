{% set raw_sba_504_foia = source('raw', 'raw_sba_504_foia') %}
{% set has_raw_uri = relation_has_column(raw_sba_504_foia, 'raw_uri') %}
{% set has_storage_backend = relation_has_column(raw_sba_504_foia, 'storage_backend') %}

with latest_successful_manifests as (
    select *
    from {{ ref('stg_ingestion_manifest') }}
    where source_system = 'sba'
      and dataset_name = '7a_504_foia'
      and resource_name like 'sba_504_%'
      and validation_status = 'passed'
      and is_latest_successful_snapshot
),

raw_rows as (
    select
        raw.*,
        {% if has_raw_uri -%}
        raw.raw_uri
        {%- else -%}
        raw.raw_file_path
        {%- endif %} as artifact_raw_uri,
        {% if has_storage_backend -%}
        raw.storage_backend
        {%- else -%}
        'local'
        {%- endif %} as artifact_storage_backend
    from {{ raw_sba_504_foia }} as raw
),

source_rows as (
    select
        raw.*,
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
            "'504'",
            "artifact_raw_uri",
            "raw_row_number",
            "locationid",
            "approvaldate",
            "grossapproval"
        ]) }} as loan_record_key,
        '504' as loan_program,
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
        {{ clean_lender_name('thirdpartylender_name') }} as lender_name,
        cast(null as varchar) as lender_fdic_number,
        cast(null as varchar) as lender_ncua_number,
        nullif(trim(cast(cdc_name as varchar)), '') as cdc_name,
        upper(nullif(trim(cast(cdc_state as varchar)), '')) as cdc_state_abbr,
        upper(nullif(trim(cast(thirdpartylender_state as varchar)), '')) as lender_state_abbr,
        try_cast(replace(replace(cast(thirdpartydollars as varchar), ',', ''), '$', '') as decimal(18, 2)) as third_party_dollars,
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
        cast(null as decimal(18, 2)) as sba_guaranteed_approval_amount,
        {{ parse_mdy_date("nullif(trim(cast(approvaldate as varchar)), '')") }} as approval_date,
        try_cast(approvalfy as integer) as approval_fiscal_year,
        {{ parse_mdy_date("nullif(trim(cast(firstdisbursementdate as varchar)), '')") }} as first_disbursement_date,
        nullif(trim(cast(processingmethod as varchar)), '') as processing_method,
        nullif(trim(cast(subprogram as varchar)), '') as subprogram,
        cast(null as decimal(9, 4)) as initial_interest_rate,
        cast(null as varchar) as fixed_or_variable_interest_indicator,
        try_cast(terminmonths as integer) as term_months,
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
        cast(null as varchar) as revolver_status,
        try_cast(jobssupported as integer) as jobs_supported,
        nullif(trim(cast(collateralind as varchar)), '') as collateral_indicator,
        cast(null as varchar) as sold_secondary_market_indicator,
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

select *
from standardized
