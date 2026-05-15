{% macro relation_has_column(relation, column_name) -%}
    {%- set columns = adapter.get_columns_in_relation(relation) -%}
    {%- set column_names = columns | map(attribute='name') | map('lower') | list -%}
    {{ return(column_name | lower in column_names) }}
{%- endmacro %}
