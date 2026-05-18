with pipeline_runs as (
    select
        pipeline_run_ids,
        loaded_at_utc,
        raw_table_count,
        validation_status
    from {{ ref('stg_pipeline_run_summary') }}
),

validation_rollup as (
    select
        sum(failed_check_count) as failed_check_count,
        sum(warning_check_count) as warning_check_count,
        sum(passed_check_count) as passed_check_count,
        max(latest_checked_at_utc) as latest_checked_at_utc
    from {{ ref('mart_pipeline_validation_summary') }}
),

source_rollup as (
    select
        count(*) as source_resource_count,
        sum(case when freshness_status = 'current' then 1 else 0 end) as current_source_resource_count,
        sum(case when freshness_status != 'current' then 1 else 0 end) as stale_or_unknown_source_resource_count
    from {{ ref('mart_pipeline_source_freshness') }}
)

select
    pipeline_runs.pipeline_run_ids,
    pipeline_runs.loaded_at_utc,
    pipeline_runs.raw_table_count,
    pipeline_runs.validation_status,
    validation_rollup.failed_check_count,
    validation_rollup.warning_check_count,
    validation_rollup.passed_check_count,
    validation_rollup.latest_checked_at_utc,
    source_rollup.source_resource_count,
    source_rollup.current_source_resource_count,
    source_rollup.stale_or_unknown_source_resource_count,
    case
        when pipeline_runs.validation_status = 'passed'
         and coalesce(validation_rollup.failed_check_count, 0) = 0
         and coalesce(source_rollup.stale_or_unknown_source_resource_count, 0) = 0
            then 'success'
        when coalesce(validation_rollup.failed_check_count, 0) > 0
            then 'failed'
        else 'warning'
    end as latest_run_status
from pipeline_runs
cross join validation_rollup
cross join source_rollup
