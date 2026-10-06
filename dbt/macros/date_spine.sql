{# Date spine macro generates a contiguous day-level calendar for the active target adapter. #}

{% macro date_spine(start_date, end_date) -%}
    {%- if target.type == 'snowflake' -%}
        with recursive spine(date_day) as (
            select cast({{ start_date }} as date)
            union all
            select dateadd(day, 1, date_day)
            from spine
            where date_day < cast({{ end_date }} as date)
        )

        select date_day
        from spine
    {%- else -%}
        select generated_date::date as date_day
        from generate_series(
            cast({{ start_date }} as date),
            cast({{ end_date }} as date),
            interval 1 day
        ) as spine(generated_date)
    {%- endif -%}
{%- endmacro %}
