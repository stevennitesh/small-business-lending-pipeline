"""Power BI model contract validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipelines.powerbi.export_schema import (
    BI_EXPORT_TABLES,
    EXTRA_SBA_KPI_BI_TABLES,
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
    *EXTRA_SBA_KPI_BI_TABLES,
}
REQUIRED_FILTERS = {"year", "state", "region", "program", "industry", "lender"}
ALLOWED_MEASURE_CATEGORIES = {"display_logic", "formatting", "dynamic_title"}


@dataclass(frozen=True)
class PowerBIModelValidation:
    """Summary of a validated source-controlled Power BI model contract."""

    model_path: str
    table_count: int
    relationship_count: int
    filter_coverage: list[str]
    artifact_status: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model validation summary for CLI output."""
        return asdict(self)


def validate_powerbi_model(
    model_path: Path | str = MODEL_PATH,
) -> PowerBIModelValidation:
    """Validate the source-controlled Power BI model contract."""
    resolved_model_path = Path(model_path)
    model = json.loads(resolved_model_path.read_text(encoding="utf-8"))

    tables = {table["name"]: table for table in model.get("tables", [])}
    missing_tables = sorted(set(BI_EXPORT_TABLES) - set(tables))
    if missing_tables:
        raise ValueError(
            "Power BI model is missing export tables: " + ", ".join(missing_tables)
        )

    missing_required = sorted(REQUIRED_IMPLEMENTATION_TABLES - set(tables))
    if missing_required:
        raise ValueError(
            "Power BI model is missing required implementation tables: "
            + ", ".join(missing_required)
        )

    for table_name, table in tables.items():
        _validate_table_source(table_name, table)
        _validate_required_columns(table_name, table)

    # These checks enforce the report boundary: Power BI handles relationships,
    # filters, and display-only measures while dbt owns core KPI calculations.
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
    """Require model sources to use BI exports or Snowflake BI tables."""
    local_csv = table.get("local_csv", "")
    normalized_csv = local_csv.replace("\\", "/").lower()
    # The dashboard must not connect directly to raw files or raw schemas; all
    # source paths should point at modeled BI outputs.
    if "/raw/" in normalized_csv or normalized_csv.startswith("data/raw/"):
        raise ValueError(f"Power BI table {table_name} points at raw data: {local_csv}")
    if not normalized_csv.startswith("data/exports/powerbi/"):
        raise ValueError(
            f"Power BI table {table_name} must use data/exports/powerbi: {local_csv}"
        )

    snowflake_table = table.get("snowflake_table", "")
    if ".RAW." in snowflake_table.upper():
        raise ValueError(
            f"Power BI table {table_name} points at a raw Snowflake table."
        )
    if "${SNOWFLAKE_BI_SCHEMA}" not in snowflake_table:
        raise ValueError(
            f"Power BI table {table_name} must point at the Snowflake BI schema."
        )


def _validate_required_columns(table_name: str, table: dict) -> None:
    """Validate required and prohibited fields for one model table."""
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
    """Require the model to expose the expected dashboard filters."""
    missing_filters = sorted(REQUIRED_FILTERS - set(model.get("filter_coverage", [])))
    if missing_filters:
        raise ValueError(
            "Power BI model is missing filters: " + ", ".join(missing_filters)
        )


def _validate_relationships(model: dict, tables: dict[str, dict]) -> None:
    """Validate supported Power BI relationship shape and endpoints."""
    dimensions = {dimension["name"] for dimension in model.get("dimensions", [])}
    table_names = set(tables)

    for relationship in model.get("relationships", []):
        if relationship.get("cardinality") != "one_to_many":
            raise ValueError(f"Unsupported relationship cardinality: {relationship}")
        if relationship.get("cross_filter") != "single":
            raise ValueError(
                f"Unsupported relationship filter direction: {relationship}"
            )

        from_table = relationship["from"].split(".", maxsplit=1)[0]
        to_table = relationship["to"].split(".", maxsplit=1)[0]
        if from_table not in dimensions:
            raise ValueError(
                f"Relationship does not start from a dimension: {relationship}"
            )
        if to_table not in table_names:
            raise ValueError(
                f"Relationship target table is not declared: {relationship}"
            )


def _validate_measures(model: dict, table_names: set[str]) -> None:
    """Validate allowed measure categories and declared table references."""
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
    """Extract table names referenced by DAX-style table[column] expressions."""
    # The validator only needs table references, not a full DAX parser; this
    # catches both quoted and bare table names before a column accessor.
    return {
        quoted_table or bare_table
        for quoted_table, bare_table in re.findall(
            r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))\s*\[",
            expression,
        )
    }
