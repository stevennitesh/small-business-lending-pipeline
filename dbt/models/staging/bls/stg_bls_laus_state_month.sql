{% set raw_bls_laus_state_month = source('raw', 'raw_bls_laus_state_month') %}

with latest_successful_manifests as (
    select
        pipeline_run_id,
        resource_name,
        raw_uri
    from {{ ref('stg_ingestion_manifest') }}
    where source_system = 'bls'
      and dataset_name = 'laus'
      and resource_name = 'laus_state_month'
      and validation_status = 'passed'
      and is_latest_successful_snapshot
),

raw_rows as (
    select
        raw.series_id,
        raw.state_fips,
        raw.state_abbr,
        raw.state_name,
        raw.observed_month,
        raw.value,
        raw.year,
        raw.period,
        raw.footnotes,
        raw.pipeline_run_id,
        raw.source_system,
        raw.source_dataset,
        raw.source_resource_name,
        raw.ingestion_date,
        raw.raw_file_path,
        raw.sha256_checksum,
        raw.raw_uri as artifact_raw_uri,
        raw.storage_backend as artifact_storage_backend
    from {{ raw_bls_laus_state_month }} as raw
)

select
    raw.series_id,
    lpad(cast(raw.state_fips as varchar), 2, '0') as state_fips,
    raw.state_abbr,
    raw.state_name as source_state_name,
    ref_state.state_name,
    case
        when nullif(trim(cast(raw.state_fips as varchar)), '') is null then 'missing'
        when ref_state.state_fips is null then 'unmapped'
        else 'mapped'
    end as state_match_status,
    try_cast(raw.observed_month as date) as observed_month,
    'unemployment_rate' as measure_name,
    try_cast(cast(raw.value as varchar) as decimal(9, 4)) / 100.0 as unemployment_rate,
    try_cast(raw.year as integer) as year,
    raw.period,
    raw.footnotes,
    raw.pipeline_run_id,
    raw.source_system,
    raw.source_dataset,
    raw.source_resource_name,
    raw.ingestion_date,
    raw.artifact_storage_backend as storage_backend,
    raw.artifact_raw_uri as raw_uri,
    raw.raw_file_path,
    raw.sha256_checksum
from raw_rows as raw
inner join latest_successful_manifests as manifest
    on raw.pipeline_run_id = manifest.pipeline_run_id
   and raw.source_resource_name = manifest.resource_name
   and raw.artifact_raw_uri = manifest.raw_uri
left join {{ ref('ref_state') }} as ref_state
    on lpad(cast(raw.state_fips as varchar), 2, '0') = lpad(cast(ref_state.state_fips as varchar), 2, '0')
