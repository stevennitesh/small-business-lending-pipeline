select
    {{ generate_surrogate_key([
        "'laus_state_month'",
        "state_fips",
        "observed_month",
        "measure_name"
    ]) }} as laus_state_month_fact_key,
    state_fips as state_key,
    {{ date_key('observed_month') }} as date_key,
    source_file.source_file_key,
    series_id,
    observed_month,
    measure_name,
    unemployment_rate,
    year,
    period,
    laus.pipeline_run_id,
    laus.source_resource_name,
    laus.raw_file_path,
    laus.sha256_checksum
from {{ ref('stg_bls_laus_state_month') }} as laus
left join {{ ref('dim_source_file') }} as source_file
    on laus.raw_file_path = source_file.raw_file_path
