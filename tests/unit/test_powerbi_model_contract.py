from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.export_powerbi_tables import BI_EXPORT_TABLES, REQUIRED_EXPORT_COLUMNS
from scripts.validate_powerbi_model import REQUIRED_FILTERS, validate_powerbi_model


MODEL_PATH = Path("powerbi/lending_dashboard_model.json")
POWER_QUERY_PATH = Path("powerbi/power_query/local_csv_queries.pq")


def test_powerbi_model_contract_validates():
    summary = validate_powerbi_model(MODEL_PATH)

    assert summary.table_count == len(BI_EXPORT_TABLES)
    assert set(summary.filter_coverage) == REQUIRED_FILTERS
    assert summary.artifact_status == "source_model_ready_pbix_requires_power_bi_desktop"


def test_powerbi_model_sources_match_export_contract():
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    tables = {table["name"]: table for table in model["tables"]}

    assert set(tables) == set(BI_EXPORT_TABLES)
    for table_name, required_columns in REQUIRED_EXPORT_COLUMNS.items():
        table = tables[table_name]
        assert table["local_csv"] == f"data/exports/powerbi/{table_name}.csv"
        assert required_columns <= set(table["required_columns"])
        assert "RAW" not in table["snowflake_table"].upper()
        assert "${SNOWFLAKE_BI_SCHEMA}" in table["snowflake_table"]


def test_power_query_sources_match_export_contract():
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
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))

    assert model["relationships"]
    assert {
        relationship["cardinality"] for relationship in model["relationships"]
    } == {"one_to_many"}
    assert {relationship["cross_filter"] for relationship in model["relationships"]} == {
        "single"
    }
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
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    tables = {table["name"] for table in model["tables"]}

    for dimension in model["dimensions"]:
        assert dimension["name"] == dimension["source_table"]
        assert dimension["source_table"] in tables


def test_powerbi_measures_are_display_only():
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))

    assert model["measures"]
    assert {measure["category"] for measure in model["measures"]} <= {
        "display_logic",
        "formatting",
        "dynamic_title",
    }
    measure_expressions = "\n".join(
        measure["expression"] for measure in model["measures"]
    )
    assert "dim_year[" not in measure_expressions
    assert "dim_state[" not in measure_expressions


def test_powerbi_measure_references_must_use_declared_tables(tmp_path):
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    model["measures"][0]["expression"] = (
        'COALESCE(SELECTEDVALUE(dim_year[year]), "All years")'
    )
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")

    with pytest.raises(ValueError, match="undeclared tables: dim_year"):
        validate_powerbi_model(model_path)
