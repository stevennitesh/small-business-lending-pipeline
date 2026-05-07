with raw_runs as (
    select
        pipeline_run_ids,
        loaded_at_utc,
        try_cast(raw_table_count as integer) as raw_table_count,
        validation_status
    from {{ source('raw', 'raw_pipeline_run_summary') }}
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
    raw_runs.pipeline_run_ids,
    raw_runs.loaded_at_utc,
    raw_runs.raw_table_count,
    raw_runs.validation_status,
    validation_rollup.failed_check_count,
    validation_rollup.warning_check_count,
    validation_rollup.passed_check_count,
    validation_rollup.latest_checked_at_utc,
    source_rollup.source_resource_count,
    source_rollup.current_source_resource_count,
    source_rollup.stale_or_unknown_source_resource_count,
    case
        when raw_runs.validation_status = 'passed'
         and coalesce(validation_rollup.failed_check_count, 0) = 0
         and coalesce(source_rollup.stale_or_unknown_source_resource_count, 0) = 0
            then 'success'
        when coalesce(validation_rollup.failed_check_count, 0) > 0
            then 'failed'
        else 'warning'
    end as latest_run_status
from raw_runs
cross join validation_rollup
cross join source_rollup
