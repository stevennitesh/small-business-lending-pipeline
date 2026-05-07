{% macro date_spine(start_date, end_date) -%}
    select generated_date::date as date_day
    from generate_series(
        cast({{ start_date }} as date),
        cast({{ end_date }} as date),
        interval 1 day
    ) as spine(generated_date)
{%- endmacro %}
