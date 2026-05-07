{% test non_negative(model, column_name) %}
    select *
    from {{ model }}
    where {{ column_name }} < 0
{% endtest %}

{% test accepted_range(model, column_name, min_value=none, max_value=none) %}
    select *
    from {{ model }}
    where
        {% if min_value is not none %}
            {{ column_name }} < {{ min_value }}
        {% endif %}
        {%- if min_value is not none and max_value is not none %}
            or
        {% endif %}
        {%- if max_value is not none %}
            {{ column_name }} > {{ max_value }}
        {%- endif %}
{% endtest %}

{% test unique_combination_of_columns(model, combination_of_columns) %}
    select
        {{ combination_of_columns | join(", ") }},
        count(*) as duplicate_count
    from {{ model }}
    group by {{ combination_of_columns | join(", ") }}
    having count(*) > 1
{% endtest %}

{% test not_empty(model) %}
    select 'model has no rows' as failure
    where not exists (
        select 1
        from {{ model }}
    )
{% endtest %}
