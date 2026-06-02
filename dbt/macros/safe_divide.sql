{# Safe division helper keeps ratio logic null-safe and consistent across KPI models. #}

{% macro safe_divide(numerator, denominator) -%}
    case
        when {{ denominator }} is null or {{ denominator }} = 0 then null
        else ({{ numerator }}) / ({{ denominator }})
    end
{%- endmacro %}
