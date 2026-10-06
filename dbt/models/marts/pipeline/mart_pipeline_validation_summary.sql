-- Pipeline mart: summarize validation, freshness, and run status for operational monitoring.

select
    pipeline_run_id,
    source_system,
    source_dataset,
    source_resource_name,
    count(*) as validation_check_count,
    sum(case when status = 'failed' then 1 else 0 end) as failed_check_count,
    sum(case when status = 'warning' then 1 else 0 end) as warning_check_count,
    sum(case when status = 'passed' then 1 else 0 end) as passed_check_count,
    max(checked_at_utc) as latest_checked_at_utc,
    case
        when sum(case when status = 'failed' then 1 else 0 end) > 0 then 'failed'
        when sum(case when status = 'warning' then 1 else 0 end) > 0 then 'warning'
        else 'passed'
    end as validation_status
from {{ ref('stg_validation_result') }}
group by 1, 2, 3, 4
