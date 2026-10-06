-- Staging model: standardize raw fields after restricting records to latest validated manifests.

select
    pipeline_run_id,
    validation_check_id,
    validation_scope,
    source_system,
    source_dataset,
    source_resource_name,
    check_name,
    check_type,
    severity,
    status,
    cast(expected_value as varchar) as expected_value,
    cast(observed_value as varchar) as observed_value,
    message,
    checked_at_utc
from {{ source('raw', 'raw_validation_result') }}
