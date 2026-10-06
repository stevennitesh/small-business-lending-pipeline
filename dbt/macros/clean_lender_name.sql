{# Lender-name macros centralize whitespace and case normalization across staging and dimension models. #}

{% macro normalize_whitespace(expression) -%}
    {%- if target.type == 'snowflake' -%}
        regexp_replace({{ expression }}, '\\s+', ' ')
    {%- else -%}
        regexp_replace({{ expression }}, '\s+', ' ', 'g')
    {%- endif -%}
{%- endmacro %}

{% macro clean_lender_name(lender_name) -%}
    nullif(nullif(
        upper(
            trim(
                {{ normalize_whitespace("coalesce(cast(" ~ lender_name ~ " as varchar), '')") }}
            )
        ),
        ''
    ), 'UNKNOWN')
{%- endmacro %}
