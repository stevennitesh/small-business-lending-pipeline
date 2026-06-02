-- Fact model: preserve latest validated source lineage while exposing the analytical grain for marts.

select
    {{ generate_surrogate_key([
        "'bds_state_year'",
        "state_fips",
        "year"
    ]) }} as bds_state_year_fact_key,
    state_fips as state_key,
    {{ date_key(year_start_date('year')) }} as date_key,
    case
        when bds.raw_uri is null then null
        else {{ generate_surrogate_key(["bds.raw_uri"]) }}
    end as source_file_key,
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
    bds.storage_backend,
    bds.raw_uri,
    bds.raw_file_path,
    bds.sha256_checksum
from {{ ref('stg_census_bds_state_year') }} as bds
