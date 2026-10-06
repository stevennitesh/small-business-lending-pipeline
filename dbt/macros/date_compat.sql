{# Date compatibility macros keep DuckDB and Snowflake date parsing/key logic aligned. #}

{% macro parse_sba_date(expression) -%}
    {%- if target.type == 'snowflake' -%}
        coalesce(try_to_date({{ expression }}, 'MM/DD/YYYY'),
                 try_to_date({{ expression }}, 'YYYY-MM-DD'))
    {%- else -%}
        coalesce(try_strptime({{ expression }}, '%m/%d/%Y')::date,
                 try_strptime({{ expression }}, '%Y-%m-%d')::date)
    {%- endif -%}
{%- endmacro %}

{% macro year_start_date(year_expression) -%}
    {%- if target.type == 'snowflake' -%}
        date_from_parts({{ year_expression }}, 1, 1)
    {%- else -%}
        make_date({{ year_expression }}, 1, 1)
    {%- endif -%}
{%- endmacro %}

{% macro date_key(date_expression) -%}
    {%- if target.type == 'snowflake' -%}
        try_to_number(to_char({{ date_expression }}, 'YYYYMMDD'))
    {%- else -%}
        try_cast(strftime({{ date_expression }}, '%Y%m%d') as integer)
    {%- endif -%}
{%- endmacro %}

{% macro year_month_label(date_expression) -%}
    {%- if target.type == 'snowflake' -%}
        to_char({{ date_expression }}, 'YYYY-MM')
    {%- else -%}
        strftime({{ date_expression }}, '%Y-%m')
    {%- endif -%}
{%- endmacro %}
