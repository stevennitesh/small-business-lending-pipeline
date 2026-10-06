-- Power BI export model: expose dashboard-safe fields from modeled marts, not raw source tables.

with years as (
    -- Build the filter from every BI table that exposes a year so report
    -- slicers do not hide valid rows from a table with a different coverage set.
    select year
    from {{ ref('bi_executive_overview') }}

    union

    select approval_year as year
    from {{ ref('bi_state_lending_trends') }}

    union

    select approval_year as year
    from {{ ref('bi_lender_concentration') }}

    union

    select approval_year as year
    from {{ ref('bi_industry_mix') }}

    union

    select approval_year as year
    from {{ ref('bi_program_mix') }}

    union

    select year
    from {{ ref('bi_regional_business_health') }}

    union

    select approval_year as year
    from {{ ref('bi_lender_mix') }}

    union

    select approval_year as year
    from {{ ref('bi_lending_performance') }}

    union

    select approval_year as year
    from {{ ref('bi_lending_status_mix') }}

    union

    select approval_year as year
    from {{ ref('bi_lending_terms_pricing') }}

    union

    select approval_year as year
    from {{ ref('bi_lending_jobs_impact') }}
)

select
    year,
    cast(year as varchar) as year_label
from years
where year is not null
