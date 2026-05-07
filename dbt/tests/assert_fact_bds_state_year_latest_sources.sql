select fact.*
from {{ ref('fact_bds_state_year') }} as fact
inner join {{ ref('dim_source_file') }} as source_file
    on fact.source_file_key = source_file.source_file_key
where not source_file.is_latest_successful_snapshot
