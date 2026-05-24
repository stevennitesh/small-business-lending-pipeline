select
    {{ generate_surrogate_key([
        "'laus_state_month'",
        "state_fips",
        "observed_month",
        "measure_name"
    ]) }} as laus_state_month_fact_key,
    state_fips as state_key,
    {{ date_key('observed_month') }} as date_key,
    case
        when laus.raw_uri is null then null
        else {{ generate_surrogate_key(["laus.raw_uri"]) }}
    end as source_file_key,
    series_id,
    observed_month,
    measure_name,
    unemployment_rate,
    year,
    period,
    laus.pipeline_run_id,
    laus.source_resource_name,
    laus.storage_backend,
    laus.raw_uri,
    laus.raw_file_path,
    laus.sha256_checksum
from {{ ref('stg_bls_laus_state_month') }} as laus
