with latest_by_resource as (
    select
        source_system,
        dataset_name as source_dataset,
        resource_name as source_resource_name,
        max(extracted_at_utc) as latest_extracted_at_utc,
        max(ingestion_date) as latest_ingestion_date,
        max(row_count) as latest_row_count,
        max(case when is_latest_successful_snapshot then 1 else 0 end) = 1 as is_latest_successful_snapshot,
        count(*) as observed_snapshot_count
    from {{ ref('stg_ingestion_manifest') }}
    group by 1, 2, 3
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
