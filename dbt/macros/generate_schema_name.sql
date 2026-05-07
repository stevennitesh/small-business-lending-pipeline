{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if target.type == 'snowflake' and custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- elif target.type == 'snowflake' -%}
        {{ default_schema }}
    {%- elif node.resource_type == 'seed' and custom_schema_name is not none -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}
    {%- endif -%}
{%- endmacro %}
