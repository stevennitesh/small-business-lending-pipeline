-- Source-resource reporting evidence; disconnected from lending slicers.
select
    source_system, source_dataset, source_resource_name,
    latest_extracted_at_utc, latest_ingestion_date, latest_observation_date, observation_date_basis,
    freshness_checked_at_utc, latest_row_count, observed_snapshot_count,
    is_latest_successful_snapshot, snapshot_validity_status, freshness_status,
    max_extract_age_days, max_observation_age_days, extract_age_days, observation_age_days,
    publication_reference_date, publication_date, publication_verified_date, publication_source_url, publication_cadence, next_scheduled_release_date, max_release_check_age_days, release_check_age_days, publication_status, download_status, freshness_reason
from {{ ref('mart_pipeline_source_freshness') }}
