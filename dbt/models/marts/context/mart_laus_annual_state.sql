-- Mean observed monthly SA rates; match expected month identities before classifying gaps.
{% set policy = var('reporting_policy') %}
with elapsed as (
    select state_key, year, observed_month, unemployment_rate,
        case when year > extract(year from cast('{{ policy.bls_observation_end }}' as date)) then 0
             when year = extract(year from cast('{{ policy.bls_observation_end }}' as date))
             then extract(month from cast('{{ policy.bls_observation_end }}' as date))
             else 12 end as expected_elapsed_month_count
    from {{ ref('fact_laus_state_month') }}
),
monthly as (
    select state_key, year, observed_month, unemployment_rate, expected_elapsed_month_count,
        {% if policy.bls_publisher_omissions %}
        case when
        {% for item in policy.bls_publisher_omissions %}
            (year = {{ item.year }} and extract(month from observed_month) = {{ item.month }})
            {% if not loop.last %} or {% endif %}
        {% endfor %}
        then true else false end
        {% else %} false {% endif %} as is_publisher_omitted_month
    from elapsed
),
annual as (
    select state_key, year, avg(unemployment_rate) as annual_average_unemployment_rate,
        count(distinct case when unemployment_rate is not null then observed_month end) as observed_month_count,
        count(distinct case when unemployment_rate is not null
            and extract(month from observed_month) <= expected_elapsed_month_count
            and not is_publisher_omitted_month then observed_month end) as observed_expected_month_count,
        count(distinct case when unemployment_rate is not null
            and (extract(month from observed_month) > expected_elapsed_month_count
                 or is_publisher_omitted_month) then observed_month end) as unexpected_month_count,
        count(distinct case when unemployment_rate is not null and is_publisher_omitted_month
            and extract(month from observed_month) <= expected_elapsed_month_count
            then observed_month end) as unexpected_publisher_month_count,
        min(observed_month) as first_observed_month, max(observed_month) as last_observed_month,
        max(expected_elapsed_month_count) as expected_elapsed_month_count
    from monthly group by 1, 2
),
coverage as (
    select state_key, year, annual_average_unemployment_rate,
        observed_month_count, observed_expected_month_count, unexpected_month_count,
        first_observed_month, last_observed_month, 12 as full_year_month_count,
        expected_elapsed_month_count,
        0
        {% for item in policy.bls_publisher_omissions %}
        + case when year = {{ item.year }} and {{ item.month }} <= expected_elapsed_month_count then 1 else 0 end
        {% endfor %} as publisher_omitted_month_count,
        unexpected_publisher_month_count,
        year = extract(year from cast('{{ policy.bls_observation_end }}' as date))
            and expected_elapsed_month_count < 12 as is_year_to_date
    from annual
),
classified as (
    select state_key, year, annual_average_unemployment_rate,
        observed_month_count, observed_expected_month_count, unexpected_month_count,
        first_observed_month, last_observed_month, full_year_month_count, expected_elapsed_month_count,
        expected_elapsed_month_count - publisher_omitted_month_count as expected_month_count,
        publisher_omitted_month_count, is_year_to_date,
        expected_elapsed_month_count - publisher_omitted_month_count - observed_expected_month_count as missing_month_count,
        observed_expected_month_count = 12 and unexpected_month_count = 0
            and publisher_omitted_month_count = 0 and not is_year_to_date
            and year <= extract(year from cast('{{ policy.bls_observation_end }}' as date)) as is_comparable_annual,
        case when unexpected_publisher_month_count > 0 then 'policy_conflict'
             when year > extract(year from cast('{{ policy.bls_observation_end }}' as date)) then 'outside_coverage_evidence'
             when unexpected_month_count > 0 or observed_expected_month_count != expected_elapsed_month_count - publisher_omitted_month_count
                 then 'missing_or_unexpected_months'
             when publisher_omitted_month_count > 0 then 'publisher_omission'
             when is_year_to_date then 'year_to_date' else 'full_year' end as annual_coverage_status
    from coverage
),
compared as (
    select state_key, year, annual_average_unemployment_rate,
        observed_month_count, observed_expected_month_count, unexpected_month_count,
        first_observed_month, last_observed_month, full_year_month_count,
        expected_elapsed_month_count, expected_month_count, publisher_omitted_month_count,
        missing_month_count, is_year_to_date, is_comparable_annual, annual_coverage_status,
        lag(year) over (partition by state_key order by year) as prior_year,
        lag(is_comparable_annual) over (partition by state_key order by year) as prior_is_comparable,
        lag(annual_average_unemployment_rate) over (partition by state_key order by year) as prior_rate
    from classified
)
select
    compared.state_key, state.state_name, year, annual_average_unemployment_rate,
    observed_month_count, observed_expected_month_count, unexpected_month_count,
    first_observed_month, last_observed_month, full_year_month_count,
    expected_elapsed_month_count, expected_month_count, publisher_omitted_month_count,
    missing_month_count, is_year_to_date, is_comparable_annual, annual_coverage_status,
    case when is_comparable_annual and prior_is_comparable and prior_year = year - 1
         then (annual_average_unemployment_rate - prior_rate) * 100 end as unemployment_rate_yoy_change_pp
from compared
left join {{ ref('dim_state') }} as state on compared.state_key = state.state_key
