select
    run_summary.pipeline_run_ids,
    run_summary.loaded_at_utc,
    run_summary.latest_run_status,
    run_summary.validation_status,
    run_summary.failed_check_count,
    run_summary.warning_check_count,
    run_summary.passed_check_count,
    run_summary.source_resource_count,
    run_summary.current_source_resource_count,
    run_summary.stale_or_unknown_source_resource_count,
    case
        when run_summary.stale_or_unknown_source_resource_count = 0 then 'current'
        when run_summary.stale_or_unknown_source_resource_count is null then 'unknown'
        else 'needs_attention'
    end as freshness_status
from {{ ref('mart_pipeline_run_summary') }} as run_summary
