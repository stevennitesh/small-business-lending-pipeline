-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

select
    run_summary.pipeline_run_ids,
    run_summary.loaded_at_utc,
    run_summary.latest_run_status,
    run_summary.raw_load_status,
    run_summary.final_pipeline_status_evidence,
    run_summary.freshness_checked_at_utc,
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
        else 'stale_or_unknown'
    end as freshness_status
from {{ ref('mart_pipeline_run_summary') }} as run_summary
