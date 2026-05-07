{% macro generate_surrogate_key(fields) -%}
    {%- set expressions = [] -%}
    {%- for field in fields -%}
        {%- do expressions.append("coalesce(cast(" ~ field ~ " as varchar), '')") -%}
    {%- endfor -%}
    md5({{ expressions | join(" || '|' || ") }})
{%- endmacro %}
