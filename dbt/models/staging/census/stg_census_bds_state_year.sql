-- Staging model: standardize raw fields after restricting records to latest validated manifests.

{% set raw_census_bds_state_year = source('raw', 'raw_census_bds_state_year') %}

with latest_successful_manifests as (
    select
        pipeline_run_id,
        resource_name,
        raw_uri
    from {{ ref('stg_ingestion_manifest') }}
    where source_system = 'census'
      and dataset_name = 'bds'
      and resource_name = 'bds_state_year'
      and validation_status = 'passed'
      and is_latest_successful_snapshot
),

raw_rows as (
    select
        raw.state,
        raw.name,
        raw.year,
        raw.estab,
        raw.estabs_entry,
        raw.estabs_entry_rate,
        raw.estabs_exit,
        raw.estabs_exit_rate,
        raw.firm,
        raw.job_creation,
        raw.job_destruction,
        raw.pipeline_run_id,
        raw.source_system,
        raw.source_dataset,
        raw.source_resource_name,
        raw.ingestion_date,
        raw.raw_file_path,
        raw.sha256_checksum,
        raw.raw_uri as artifact_raw_uri,
        raw.storage_backend as artifact_storage_backend
    from {{ raw_census_bds_state_year }} as raw
)

select
    lpad(cast(raw.state as varchar), 2, '0') as state_fips,
    raw.name as source_state_name,
    ref_state.state_name as state_name,
    case
        when nullif(trim(cast(raw.state as varchar)), '') is null then 'missing'
        when ref_state.state_fips is null then 'unmapped'
        else 'mapped'
    end as state_match_status,
    try_cast(raw.year as integer) as year,
    try_cast(raw.estab as integer) as establishments,
    try_cast(raw.estabs_entry as integer) as establishment_entries,
    try_cast(raw.estabs_entry_rate as decimal(12, 4)) / 100.0 as establishment_entry_rate,
    try_cast(raw.estabs_exit as integer) as establishment_exits,
    try_cast(raw.estabs_exit_rate as decimal(12, 4)) / 100.0 as establishment_exit_rate,
    try_cast(raw.firm as integer) as firms,
    try_cast(raw.job_creation as integer) as job_creation,
    try_cast(raw.job_destruction as integer) as job_destruction,
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
    on lpad(cast(raw.state as varchar), 2, '0') = lpad(cast(ref_state.state_fips as varchar), 2, '0')
