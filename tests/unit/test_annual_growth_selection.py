"""Check the sparse-state counterexample and the guarded Desktop handoff."""

import json
from pathlib import Path

import duckdb
import pytest

from pipelines.powerbi.model_contract import validate_powerbi_model
from tests.unit.test_reporting_methodology import render_model


def _growth_model():
    model = json.loads(Path("powerbi/lending_dashboard_model.json").read_text())
    measure = next(
        m for m in model["measures"] if m.get("aggregation") == "full_year_growth"
    )
    return model, measure


def test_prior_only_state_is_visible_in_prior_population_even_when_current_rows_are_comparable():
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute("insert into dim_state values ('01', 'Alabama'), ('02', 'Alaska')")
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',2024,100,date '2024-06-01'), ('02',2024,900,date '2024-06-01'),
            ('01',2025,110,date '2025-06-01'))
            as t(project_state_key,approval_year,gross_approval_amount,approval_date)""")
        rows = con.execute(
            render_model("dbt/models/marts/lending/mart_lending_annual_state.sql")
        ).df()
    current = rows.loc[rows.approval_year.eq(2025)]
    prior = rows.loc[rows.approval_year.eq(2024)]
    assert current.is_comparable_yoy.all()  # The former guard alone would pass.
    assert (
        current.total_approved_loan_amount.sum()
        / current.comparable_prior_year_amount.sum()
        - 1
        == pytest.approx(0.1)
    )
    assert set(prior.state_key) - set(current.state_key) == {"02"}
    assert set(prior.loc[prior.state_key.eq("01"), "state_key"]) == set(
        current.state_key
    )
    _, measure = _growth_model()
    expression = measure["expression"]
    assert "EXCEPT(CurrentStates, PriorStates)" in expression
    assert "EXCEPT(PriorStates, CurrentStates)" in expression
    assert "REMOVEFILTERS(bi_year_filter)" in expression
    assert "bi_year_filter[year] = SelectedYear - 1" in expression
    assert "REMOVEFILTERS(bi_state_filter)" not in expression


@pytest.mark.parametrize(
    "guard",
    [
        "COUNTROWS(EXCEPT(CurrentStates, PriorStates)) = 0 &&",
        "COUNTROWS(EXCEPT(PriorStates, CurrentStates)) = 0 &&",
    ],
)
def test_growth_contract_rejects_a_missing_population_guard(tmp_path, guard):
    model, measure = _growth_model()
    measure["expression"] = measure["expression"].replace(guard, "")
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError, match="allowed aggregation"):
        validate_powerbi_model(path)
