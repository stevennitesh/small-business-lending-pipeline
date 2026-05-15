{% set raw_ingestion_manifest = source('raw', 'raw_ingestion_manifest') %}
{% set has_storage_backend = relation_has_column(raw_ingestion_manifest, 'storage_backend') %}
{% set has_raw_uri = relation_has_column(raw_ingestion_manifest, 'raw_uri') %}

with manifests as (
    select
        *,
        validation_status = 'passed'
        and dense_rank() over (
            partition by source_system, dataset_name, resource_name
            order by extracted_at_utc desc, ingestion_date desc, pipeline_run_id desc
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
    {%- if has_storage_backend %}
    storage_backend,
    {%- else %}
    case
        when nullif(s3_raw_uri, '') is not null
            and nullif(local_raw_path, '') is null
            then 's3'
        else 'local'
    end as storage_backend,
    {%- endif %}
    {%- if has_raw_uri %}
    raw_uri,
    {%- else %}
    coalesce(nullif(local_raw_path, ''), nullif(s3_raw_uri, '')) as raw_uri,
    {%- endif %}
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
