-- Staging model: standardize raw fields after restricting records to latest validated manifests.

{% set raw_ingestion_manifest = source('raw', 'raw_ingestion_manifest') %}

with manifests as (
    select
        pipeline_run_id,
        source_system,
        dataset_name,
        resource_name,
        source_url,
        extracted_at_utc,
        ingestion_date,
        storage_backend,
        raw_uri,
        local_raw_path,
        s3_raw_uri,
        file_format,
        row_count,
        sha256_checksum,
        schema_hash,
        validation_status,
        request_parameters,
        column_count,
        file_size_bytes,
        validation_messages,
        -- Latest snapshots are gated by validation status so downstream facts
        -- never report from a newer but failed raw extract.
        validation_status = 'passed'
        and row_number() over (
            partition by source_system, dataset_name, resource_name
            order by case when validation_status = 'passed' then 0 else 1 end,
                extracted_at_utc desc, ingestion_date desc, pipeline_run_id desc, raw_uri desc
        ) = 1 as is_latest_successful_snapshot
    from {{ raw_ingestion_manifest }}
)

select
    pipeline_run_id,
    source_system,
    dataset_name,
    resource_name,
    source_url,
    extracted_at_utc,
    ingestion_date,
    storage_backend,
    raw_uri,
    local_raw_path,
    s3_raw_uri,
    file_format,
    try_cast(row_count as integer) as row_count,
    sha256_checksum,
    schema_hash,
    validation_status,
    request_parameters,
    try_cast(column_count as integer) as column_count,
    try_cast(file_size_bytes as bigint) as file_size_bytes,
    validation_messages,
    is_latest_successful_snapshot
from manifests
