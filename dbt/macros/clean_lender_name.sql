{% macro clean_lender_name(lender_name) -%}
    nullif(
        upper(
            trim(
                regexp_replace(
                    coalesce(cast({{ lender_name }} as varchar), ''),
                    '\\s+',
                    ' ',
                    'g'
                )
            )
        ),
        ''
    )
{%- endmacro %}
