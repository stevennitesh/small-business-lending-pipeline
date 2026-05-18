select
    pipeline_run_ids,
    loaded_at_utc,
    try_cast(raw_table_count as integer) as raw_table_count,
    validation_status
from {{ source('raw', 'raw_pipeline_run_summary') }}
