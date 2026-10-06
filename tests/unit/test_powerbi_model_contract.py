from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipelines.powerbi.export_schema import BI_EXPORT_TABLES, REQUIRED_EXPORT_COLUMNS
from pipelines.powerbi.model_contract import REQUIRED_FILTERS, validate_powerbi_model


MODEL_PATH = Path("powerbi/lending_dashboard_model.json")
POWER_QUERY_PATH = Path("powerbi/power_query/local_csv_queries.pq")


def _read_model() -> dict:
    """Read model for tests."""
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def test_powerbi_model_contract_validates():
    """Validate that Power BI model contract validates."""
    summary = validate_powerbi_model(MODEL_PATH)

    assert summary.table_count == len(BI_EXPORT_TABLES)
    assert set(summary.filter_coverage) == REQUIRED_FILTERS
    assert (
        summary.artifact_status == "source_model_ready_pbix_requires_power_bi_desktop"
    )
    assert summary.to_dict()["model_path"] == str(MODEL_PATH)


def test_powerbi_model_sources_match_export_contract():
    """Validate that Power BI model sources match export contract."""
    model = _read_model()
    tables = {table["name"]: table for table in model["tables"]}

    assert set(tables) == set(BI_EXPORT_TABLES)
    for table_name, required_columns in REQUIRED_EXPORT_COLUMNS.items():
        table = tables[table_name]
        assert table["local_csv"] == f"data/exports/powerbi/{table_name}.csv"
        assert required_columns <= set(table["required_columns"])
        assert "RAW" not in table["snowflake_table"].upper()
        assert "${SNOWFLAKE_BI_SCHEMA}" in table["snowflake_table"]


def test_power_query_sources_match_export_contract():
    """Validate that power query sources match export contract."""
    power_query = POWER_QUERY_PATH.read_text(encoding="utf-8")
    assert "ExportRoot" in power_query
    loaded_tables = {
        table_name
        for alias, table_name in re.findall(
            r"(\w+)\s*=\s*LoadCsv\(\"([^\"]+)\"\)",
            power_query,
        )
        if alias == table_name
    }

    assert loaded_tables == set(BI_EXPORT_TABLES)


def test_powerbi_relationships_are_single_direction_one_to_many():
    """Validate that Power BI relationships are single direction one to many."""
    model = _read_model()

    assert model["relationships"]
    assert {relationship["cardinality"] for relationship in model["relationships"]} == {
        "one_to_many"
    }
    assert {
        relationship["cross_filter"] for relationship in model["relationships"]
    } == {"single"}
    assert {
        relationship["from"].split(".", maxsplit=1)[0]
        for relationship in model["relationships"]
    } <= {
        "bi_state_filter",
        "bi_year_filter",
        "bi_loan_program_filter",
        "bi_naics_filter",
        "bi_lender_filter",
    }


def test_powerbi_dimensions_use_declared_filter_tables():
    """Validate that Power BI dimensions use declared filter tables."""
    model = _read_model()
    tables = {table["name"] for table in model["tables"]}

    for dimension in model["dimensions"]:
        assert dimension["name"] == dimension["source_table"]
        assert dimension["source_table"] in tables


def test_powerbi_measures_use_modeled_components():
    """Validate semantic and display measures stay within modeled BI components."""
    model = _read_model()

    assert model["measures"]
    assert {measure["category"] for measure in model["measures"]} <= {
        "display_logic",
        "formatting",
        "dynamic_title",
        "semantic_aggregation",
    }
    measure_expressions = "\n".join(
        measure["expression"] for measure in model["measures"]
    )
    assert "dim_year[" not in measure_expressions
    assert "dim_state[" not in measure_expressions


def test_powerbi_measure_references_must_use_declared_tables(tmp_path):
    """Validate that Power BI measure references must use declared tables."""
    model = _read_model()
    model["measures"][0]["expression"] = (
        'COALESCE(SELECTEDVALUE(dim_year[year]), "All years")'
    )
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")

    with pytest.raises(ValueError, match="undeclared tables: dim_year"):
        validate_powerbi_model(model_path)


@pytest.mark.parametrize(
    "expression,error",
    [
        ("SUM(bi_executive_overview[not_a_column])", "undeclared column"),
        ("[Missing Measure]", "undeclared measure"),
        ("AVERAGE(bi_executive_overview[average_loan_size])", "allowed aggregation"),
    ],
)
def test_semantic_measure_rejects_missing_dependencies_and_average_of_ratios(
    tmp_path, expression, error
):
    """Reject plausible but incorrect report aggregations and broken references."""
    model = _read_model()
    measure = next(m for m in model["measures"] if m["name"] == "Average Approval Size")
    measure["expression"] = expression
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        validate_powerbi_model(path)


def test_relationship_columns_must_exist(tmp_path):
    """A valid table name cannot conceal a broken relationship column."""
    model = _read_model()
    model["relationships"][0]["to"] = "bi_executive_overview.not_a_column"
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="endpoint is undeclared"):
        validate_powerbi_model(path)


def test_required_semantic_measures_cannot_be_silently_removed(tmp_path):
    """A handoff missing the average measure cannot pass on display labels alone."""
    model = _read_model()
    model["measures"] = [
        m for m in model["measures"] if m["name"] != "Average Approval Size"
    ]
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required semantic measures"):
        validate_powerbi_model(path)


def test_intensity_measure_cannot_include_unmatched_approval_numerator(tmp_path):
    """Reject an intensity that includes lending where BDS stock is unavailable."""
    model = _read_model()
    measure = next(
        m
        for m in model["measures"]
        if m["name"] == "Approvals per 1000 Establishment Years"
    )
    measure["expression"] = (
        "DIVIDE(SUM(bi_regional_business_health[loan_count]) * 1000, "
        "SUM(bi_regional_business_health[establishment_count]))"
    )
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="allowed aggregation"):
        validate_powerbi_model(path)


def test_industry_coverage_must_clear_known_only_page_filter(tmp_path):
    """Reject a coverage denominator that collapses to known-only displayed rows."""
    model = _read_model()
    measure = next(
        m for m in model["measures"] if m["name"] == "Industry Dollar Coverage"
    )
    measure["expression"] = (
        "DIVIDE(CALCULATE(SUM(bi_industry_mix[total_approved_loan_amount]), "
        "REMOVEFILTERS(bi_naics_filter), bi_industry_mix[is_known_industry] = TRUE()), "
        "CALCULATE(SUM(bi_industry_mix[total_approved_loan_amount]), REMOVEFILTERS(bi_naics_filter)))"
    )
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="allowed aggregation"):
        validate_powerbi_model(path)


@pytest.mark.parametrize("description", [None, "", "   "])
def test_measure_tooltip_description_is_required(tmp_path, description):
    """Every advertised tooltip must carry a useful nonblank description."""
    model = _read_model()
    model["measures"][0]["description"] = description
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="Empty Power BI measure description"):
        validate_powerbi_model(path)


@pytest.mark.parametrize(
    "name,dimension,column,noun",
    [
        ("Selected Year Label", "bi_year_filter", "year", "years"),
        ("Selected State Label", "bi_state_filter", "state_name", "states"),
    ],
)
def test_selection_label_contract_distinguishes_empty_one_all_and_subset(
    tmp_path, name, dimension, column, noun
):
    """Static DAX contract: a regional or multi-value subset cannot become All."""
    model = _read_model()
    measure = next(item for item in model["measures"] if item["name"] == name)
    expression = measure["expression"]
    assert f"COUNTROWS(VALUES({dimension}[{column}]))" in expression
    assert f"COUNTROWS(ALL({dimension}))" in expression
    assert f'SelectedCount = 0, "No {noun}"' in expression
    assert "SelectedCount = 1, " in expression
    assert f'SelectedCount = AllCount, "All {noun}"' in expression
    assert f'"Multiple {noun}"' in expression

    # Removing only the label column leaves the region filter in the all-state count.
    measure["expression"] = expression.replace(
        f"ALL({dimension})", f"ALL({dimension}[{column}])"
    )
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="Selection label must distinguish"):
        validate_powerbi_model(path)


def test_selection_label_cannot_collapse_multiple_subset_to_all(tmp_path):
    model = _read_model()
    model["measures"][0]["expression"] = (
        'COALESCE(SELECTEDVALUE(bi_year_filter[year]), "All years")'
    )
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="Selection label must distinguish"):
        validate_powerbi_model(path)
