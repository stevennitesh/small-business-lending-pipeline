-- Compare source periods with verified publications; observation age is descriptive.
{% set rules = var('source_freshness_rules') %}
{% set policy = var('reporting_policy', {}) %}
{% set bds = policy.get('census_bds_release', {}) %}
{% set publications = {
    'sba': policy.get('source_publications', {}).get('sba', {}),
    'census': bds,
    'bls': policy.get('source_publications', {}).get('bls', {})
} %}
{% set reference_dates = {
    'sba': policy.get('sba_calendar_end', ''),
    'census': (bds.get('latest_year') | string) ~ '-03-12',
    'bls': policy.get('bls_observation_end', '')
} %}
with ranked_manifest as (
    select source_system, dataset_name as source_dataset,
        resource_name as source_resource_name, extracted_at_utc, ingestion_date,
        row_count, is_latest_successful_snapshot,
        row_number() over (
            partition by source_system, dataset_name, resource_name
            order by extracted_at_utc desc, ingestion_date desc, pipeline_run_id desc
        ) as resource_snapshot_rank,
        count(*) over (partition by source_system, dataset_name, resource_name) as observed_snapshot_count
    from {{ ref('stg_ingestion_manifest') }}
),
observations as (
    select 'sba' as source_system, max(approval_date) as latest_observation_date, 'approval_date' as observation_date_basis from {{ ref('fact_sba_loans') }}
    union all
    select 'census', max(bds_reference_date), 'march_12_reference' from {{ ref('fact_bds_state_year') }}
    union all
    select 'bls', last_day(max(observed_month)), 'observation_month_end' from {{ ref('fact_laus_state_month') }}
),
publisher_evidence as (
    {% for source, evidence in publications.items() %}
    select '{{ source }}' as source_system,
        try_cast('{{ reference_dates[source] }}' as date) as publication_reference_date,
        try_cast('{{ evidence.get("released_on") or "" }}' as date) as publication_date,
        try_cast('{{ evidence.get("verified_on") or "" }}' as date) as publication_verified_date,
        nullif('{{ (evidence.get("source_url") or "") | replace("'", "''") }}', '') as publication_source_url,
        try_cast('{{ evidence.get("next_scheduled_release") or "" }}' as date) as next_scheduled_release_date,
        '{{ rules.get(source, {}).get("expected_cadence", "") }}' as publication_cadence,
        {{ rules.get(source, {}).get("max_release_check_age_days", "null") }} as max_release_check_age_days
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),
dated as (
    select manifest.source_system, source_dataset, source_resource_name,
        extracted_at_utc as latest_extracted_at_utc, ingestion_date as latest_ingestion_date,
        row_count as latest_row_count, observed_snapshot_count, is_latest_successful_snapshot,
        observations.latest_observation_date, observations.observation_date_basis,
        cast('{{ var("freshness_checked_at", run_started_at.isoformat()) }}' as timestamp) as freshness_checked_at_utc,
        case manifest.source_system
        {% for source, rule in rules.items() %}
            when '{{ source }}' then {{ rule.max_extract_age_days }}
        {% endfor %}
        end as max_extract_age_days,
        cast(null as integer) as max_observation_age_days,
        publication_reference_date, publication_date, publication_verified_date,
        publication_source_url, publication_cadence, next_scheduled_release_date,
        max_release_check_age_days
    from ranked_manifest as manifest
    left join observations on manifest.source_system = observations.source_system
    left join publisher_evidence on manifest.source_system = publisher_evidence.source_system
    where resource_snapshot_rank = 1
),
aged as (
    select
        dated.source_system, dated.source_dataset, dated.source_resource_name, dated.latest_extracted_at_utc,
        dated.latest_ingestion_date, dated.latest_row_count, dated.observed_snapshot_count, dated.is_latest_successful_snapshot,
        dated.latest_observation_date, dated.observation_date_basis, dated.freshness_checked_at_utc, dated.max_extract_age_days,
        dated.max_observation_age_days, dated.publication_reference_date, dated.publication_date, dated.publication_verified_date,
        dated.publication_source_url, dated.publication_cadence, dated.next_scheduled_release_date, dated.max_release_check_age_days,
        {{ dbt.datediff('try_cast(latest_extracted_at_utc as timestamp)', 'freshness_checked_at_utc', 'day') }} as extract_age_days,
        {{ dbt.datediff('latest_observation_date', 'cast(freshness_checked_at_utc as date)', 'day') }} as observation_age_days,
        {{ dbt.datediff('publication_verified_date', 'cast(freshness_checked_at_utc as date)', 'day') }} as release_check_age_days,
        -- SBA's reference is a release quarter, not the last approval's exact day.
        case source_system
            when 'sba' then extract(year from latest_observation_date) * 4 + extract(quarter from latest_observation_date)
            when 'census' then extract(year from latest_observation_date)
            when 'bls' then extract(year from latest_observation_date) * 12 + extract(month from latest_observation_date)
        end as saved_period,
        case source_system
            when 'sba' then extract(year from publication_reference_date) * 4 + extract(quarter from publication_reference_date)
            when 'census' then extract(year from publication_reference_date)
            when 'bls' then extract(year from publication_reference_date) * 12 + extract(month from publication_reference_date)
        end as published_period
    from dated
),
assessed as (
    select
        aged.source_system, aged.source_dataset, aged.source_resource_name, aged.latest_extracted_at_utc,
        aged.latest_ingestion_date, aged.latest_row_count, aged.observed_snapshot_count, aged.is_latest_successful_snapshot,
        aged.latest_observation_date, aged.observation_date_basis, aged.freshness_checked_at_utc, aged.max_extract_age_days,
        aged.max_observation_age_days, aged.publication_reference_date, aged.publication_date, aged.publication_verified_date,
        aged.publication_source_url, aged.publication_cadence, aged.next_scheduled_release_date, aged.max_release_check_age_days,
        aged.extract_age_days, aged.observation_age_days, aged.release_check_age_days, aged.saved_period,
        aged.published_period,
        case
            when saved_period is null or published_period is null or observation_age_days < 0
                or publication_verified_date is null or release_check_age_days < 0
                or publication_reference_date > publication_verified_date
                or max_release_check_age_days is null or max_release_check_age_days <= 0
                or publication_source_url is null
                or (source_system = 'census' and publication_date is null)
                or publication_date > publication_verified_date
                or publication_date < publication_reference_date then 'unknown'
            when release_check_age_days > max_release_check_age_days
                or (cast(freshness_checked_at_utc as date) >= next_scheduled_release_date
                    and publication_verified_date < next_scheduled_release_date) then 'verification_due'
            when saved_period < published_period then 'newer_release_available'
            when saved_period > published_period then 'unknown'
            else 'latest_published'
        end as publication_status,
        case
            when extract_age_days is null or extract_age_days < 0 or max_extract_age_days is null then 'unknown'
            when extract_age_days > max_extract_age_days then 'review_due'
            else 'current'
        end as download_status
    from aged
)
select source_system, source_dataset, source_resource_name, latest_extracted_at_utc,
    latest_ingestion_date, latest_row_count, observed_snapshot_count, is_latest_successful_snapshot,
    latest_observation_date, observation_date_basis, freshness_checked_at_utc, max_extract_age_days, max_observation_age_days,
    extract_age_days, observation_age_days,
    publication_reference_date, publication_date, publication_verified_date,
    publication_source_url, publication_cadence, next_scheduled_release_date,
    max_release_check_age_days, release_check_age_days, publication_status, download_status,
    case when is_latest_successful_snapshot then 'valid_selected_snapshot' else 'needs_attention' end as snapshot_validity_status,
    case
        when publication_status = 'newer_release_available' then 'stale'
        when publication_status = 'latest_published' and download_status = 'current' then 'latest_published'
        else 'unknown'
    end as freshness_status,
    case
        when publication_status = 'newer_release_available' then 'newer_release_available'
        when publication_status = 'verification_due' then 'publisher_verification_due'
        when publication_status = 'unknown' then 'publisher_evidence_unknown'
        when download_status = 'review_due' then 'download_review_due'
        when download_status = 'unknown' then 'download_date_unknown'
        else 'latest_verified_release'
    end as freshness_reason
from assessed
