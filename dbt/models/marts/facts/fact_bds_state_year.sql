select
    {{ generate_surrogate_key([
        "'bds_state_year'",
        "state_fips",
        "year"
    ]) }} as bds_state_year_fact_key,
    state_fips as state_key,
    {{ date_key(year_start_date('year')) }} as date_key,
    source_file.source_file_key,
    year,
    establishments,
    establishment_entries,
    establishment_entry_rate,
    establishment_exits,
    establishment_exit_rate,
    firms,
    job_creation,
    job_destruction,
    bds.pipeline_run_id,
    bds.source_resource_name,
    bds.raw_file_path,
    bds.sha256_checksum
from {{ ref('stg_census_bds_state_year') }} as bds
left join {{ ref('dim_source_file') }} as source_file
    on bds.raw_file_path = source_file.raw_file_path
