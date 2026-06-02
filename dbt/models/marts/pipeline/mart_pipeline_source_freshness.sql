-- Pipeline mart: summarize validation, freshness, and run status for operational monitoring.

with ranked_manifest as (
    select
        source_system,
        dataset_name as source_dataset,
        resource_name as source_resource_name,
        extracted_at_utc,
        ingestion_date,
        row_count,
        is_latest_successful_snapshot,
        row_number() over (
            partition by source_system, dataset_name, resource_name
            order by extracted_at_utc desc, ingestion_date desc, pipeline_run_id desc
        ) as resource_snapshot_rank,
        count(*) over (
            partition by source_system, dataset_name, resource_name
        ) as observed_snapshot_count
    from {{ ref('stg_ingestion_manifest') }}
),

latest_by_resource as (
    select
        source_system,
        source_dataset,
        source_resource_name,
        extracted_at_utc as latest_extracted_at_utc,
        ingestion_date as latest_ingestion_date,
        row_count as latest_row_count,
        is_latest_successful_snapshot,
        observed_snapshot_count
    from ranked_manifest
    where resource_snapshot_rank = 1
)

select
    source_system,
    source_dataset,
    source_resource_name,
    latest_extracted_at_utc,
    latest_ingestion_date,
    latest_row_count,
    observed_snapshot_count,
    is_latest_successful_snapshot,
    case
        when not is_latest_successful_snapshot then 'needs_attention'
        when latest_row_count is null then 'unknown'
        else 'current'
    end as freshness_status
from latest_by_resource
