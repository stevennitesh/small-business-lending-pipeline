with staging_sources as (
    select
        'stg_sba_loans' as model_name,
        pipeline_run_id,
        source_resource_name,
        raw_file_path
    from {{ ref('stg_sba_loans') }}

    union all

    select
        'stg_bls_laus_state_month' as model_name,
        pipeline_run_id,
        source_resource_name,
        raw_file_path
    from {{ ref('stg_bls_laus_state_month') }}

    union all

    select
        'stg_census_bds_state_year' as model_name,
        pipeline_run_id,
        source_resource_name,
        raw_file_path
    from {{ ref('stg_census_bds_state_year') }}
)

select staging_sources.*
from staging_sources
left join {{ ref('stg_ingestion_manifest') }} as manifest
    on staging_sources.pipeline_run_id = manifest.pipeline_run_id
   and staging_sources.source_resource_name = manifest.resource_name
   and staging_sources.raw_file_path = manifest.local_raw_path
where coalesce(manifest.is_latest_successful_snapshot, false) = false
