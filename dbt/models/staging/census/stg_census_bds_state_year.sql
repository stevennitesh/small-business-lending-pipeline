with latest_successful_manifests as (
    select *
    from {{ source('raw', 'raw_ingestion_manifest') }}
    where source_system = 'census'
      and dataset_name = 'bds'
      and resource_name = 'bds_state_year'
      and validation_status = 'passed'
    qualify dense_rank() over (
        partition by source_system, dataset_name, resource_name
        order by extracted_at_utc desc, ingestion_date desc, pipeline_run_id desc
    ) = 1
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
    try_cast(raw.estabs_entry_rate as decimal(12, 4)) as establishment_entry_rate,
    try_cast(raw.estabs_exit as integer) as establishment_exits,
    try_cast(raw.estabs_exit_rate as decimal(12, 4)) as establishment_exit_rate,
    try_cast(raw.firm as integer) as firms,
    try_cast(raw.job_creation as integer) as job_creation,
    try_cast(raw.job_destruction as integer) as job_destruction,
    raw.pipeline_run_id,
    raw.source_system,
    raw.source_dataset,
    raw.source_resource_name,
    raw.ingestion_date,
    raw.raw_file_path,
    raw.sha256_checksum
from {{ source('raw', 'raw_census_bds_state_year') }} as raw
inner join latest_successful_manifests as manifest
    on raw.pipeline_run_id = manifest.pipeline_run_id
   and raw.source_resource_name = manifest.resource_name
   and raw.raw_file_path = manifest.local_raw_path
left join {{ ref('ref_state') }} as ref_state
    on lpad(cast(raw.state as varchar), 2, '0') = lpad(cast(ref_state.state_fips as varchar), 2, '0')
