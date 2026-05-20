from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_powerbi_tables import (
    BI_EXPORT_TABLES,
    PROHIBITED_EXPORT_FIELDS,
    REQUIRED_EXPORT_COLUMNS,
)


MODEL_PATH = Path("powerbi/lending_dashboard_model.json")
REQUIRED_IMPLEMENTATION_TABLES = {
    "bi_executive_overview",
    "bi_state_lending_trends",
    "bi_lender_concentration",
    "bi_industry_mix",
    "bi_program_mix",
    "bi_regional_business_health",
    "bi_pipeline_health",
    "bi_lending_performance",
    "bi_lending_status_mix",
    "bi_lending_terms_pricing",
    "bi_lending_jobs_impact",
}
REQUIRED_FILTERS = {"year", "state", "region", "program", "industry", "lender"}
ALLOWED_MEASURE_CATEGORIES = {"display_logic", "formatting", "dynamic_title"}


@dataclass(frozen=True)
class PowerBIModelValidation:
    model_path: str
    table_count: int
    relationship_count: int
    filter_coverage: list[str]
    artifact_status: str


def validate_powerbi_model(model_path: Path | str = MODEL_PATH) -> PowerBIModelValidation:
    resolved_model_path = Path(model_path)
    model = json.loads(resolved_model_path.read_text(encoding="utf-8"))

    tables = {table["name"]: table for table in model.get("tables", [])}
    missing_tables = sorted(set(BI_EXPORT_TABLES) - set(tables))
    if missing_tables:
        raise ValueError("Power BI model is missing export tables: " + ", ".join(missing_tables))

    missing_required = sorted(REQUIRED_IMPLEMENTATION_TABLES - set(tables))
    if missing_required:
        raise ValueError(
            "Power BI model is missing required implementation tables: "
            + ", ".join(missing_required)
        )

    for table_name, table in tables.items():
        _validate_table_source(table_name, table)
        _validate_required_columns(table_name, table)

    _validate_filter_coverage(model)
    _validate_relationships(model, tables)
    _validate_measures(model, set(tables))

    return PowerBIModelValidation(
        model_path=str(resolved_model_path),
        table_count=len(tables),
        relationship_count=len(model.get("relationships", [])),
        filter_coverage=sorted(model.get("filter_coverage", [])),
        artifact_status=model["artifact_status"],
    )


def _validate_table_source(table_name: str, table: dict) -> None:
    local_csv = table.get("local_csv", "")
    normalized_csv = local_csv.replace("\\", "/").lower()
    if "/raw/" in normalized_csv or normalized_csv.startswith("data/raw/"):
        raise ValueError(f"Power BI table {table_name} points at raw data: {local_csv}")
    if not normalized_csv.startswith("data/exports/powerbi/"):
        raise ValueError(f"Power BI table {table_name} must use data/exports/powerbi: {local_csv}")

    snowflake_table = table.get("snowflake_table", "")
    if ".RAW." in snowflake_table.upper():
        raise ValueError(f"Power BI table {table_name} points at a raw Snowflake table.")
    if "${SNOWFLAKE_BI_SCHEMA}" not in snowflake_table:
        raise ValueError(
            f"Power BI table {table_name} must point at the Snowflake BI schema."
        )


def _validate_required_columns(table_name: str, table: dict) -> None:
    declared_columns = set(table.get("required_columns", []))
    prohibited_columns = sorted(PROHIBITED_EXPORT_FIELDS & declared_columns)
    if prohibited_columns:
        raise ValueError(
            f"Power BI table {table_name} exposes prohibited fields: "
            + ", ".join(prohibited_columns)
        )

    required_export_columns = REQUIRED_EXPORT_COLUMNS.get(table_name, set())
    missing_columns = sorted(required_export_columns - declared_columns)
    if missing_columns:
        raise ValueError(
            f"Power BI table {table_name} is missing required export columns: "
            + ", ".join(missing_columns)
        )


def _validate_filter_coverage(model: dict) -> None:
    missing_filters = sorted(REQUIRED_FILTERS - set(model.get("filter_coverage", [])))
    if missing_filters:
        raise ValueError("Power BI model is missing filters: " + ", ".join(missing_filters))


def _validate_relationships(model: dict, tables: dict[str, dict]) -> None:
    dimensions = {dimension["name"] for dimension in model.get("dimensions", [])}
    table_names = set(tables)

    for relationship in model.get("relationships", []):
        if relationship.get("cardinality") != "one_to_many":
            raise ValueError(f"Unsupported relationship cardinality: {relationship}")
        if relationship.get("cross_filter") != "single":
            raise ValueError(f"Unsupported relationship filter direction: {relationship}")

        from_table = relationship["from"].split(".", maxsplit=1)[0]
        to_table = relationship["to"].split(".", maxsplit=1)[0]
        if from_table not in dimensions:
            raise ValueError(f"Relationship does not start from a dimension: {relationship}")
        if to_table not in table_names:
            raise ValueError(f"Relationship target table is not declared: {relationship}")


def _validate_measures(model: dict, table_names: set[str]) -> None:
    for measure in model.get("measures", []):
        category = measure.get("category")
        if category not in ALLOWED_MEASURE_CATEGORIES:
            raise ValueError(f"Power BI measure category is not allowed: {category}")

        expression = measure.get("expression", "")
        referenced_tables = _measure_table_references(expression)
        undeclared_tables = sorted(referenced_tables - table_names)
        if undeclared_tables:
            raise ValueError(
                f"Power BI measure {measure.get('name')} references undeclared tables: "
                + ", ".join(undeclared_tables)
            )


def _measure_table_references(expression: str) -> set[str]:
    return {
        quoted_table or bare_table
        for quoted_table, bare_table in re.findall(
            r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))\s*\[",
            expression,
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Power BI model contract.")
    parser.add_argument("--model-path", default=str(MODEL_PATH))
    args = parser.parse_args()

    summary = validate_powerbi_model(args.model_path)
    print(json.dumps(summary.__dict__, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
