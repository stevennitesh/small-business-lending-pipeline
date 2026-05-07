select
    fact.state_key,
    state.state_name,
    fact.year,
    fact.establishments as establishment_count,
    fact.establishment_entries,
    fact.establishment_entry_rate,
    fact.establishment_exits,
    fact.establishment_exit_rate,
    fact.firms,
    fact.job_creation,
    fact.job_destruction
from {{ ref('fact_bds_state_year') }} as fact
left join {{ ref('dim_state') }} as state
    on fact.state_key = state.state_key
