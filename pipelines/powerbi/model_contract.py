"""Power BI model contract validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipelines.powerbi.semantic_measures import aggregation_expression, dax_handoff

from pipelines.powerbi.export_schema import (
    BI_EXPORT_TABLES,
    EXTRA_SBA_KPI_BI_TABLES,
    PROHIBITED_EXPORT_FIELDS,
    REQUIRED_EXPORT_COLUMNS,
)


MODEL_PATH = Path("powerbi/lending_dashboard_model.json")


def selection_label_expression(name: str) -> str:
    """Approved display-only selection labels clear the entire dimension for all."""
    dimension, column, noun = {
        "Selected Year Label": ("bi_year_filter", "year", "years"),
        "Selected State Label": ("bi_state_filter", "state_name", "states"),
    }[name]
    single = f"SELECTEDVALUE({dimension}[{column}])"
    if noun == "years":
        single = f'FORMAT({single}, "0")'
    return f"""VAR SelectedCount = COUNTROWS(VALUES({dimension}[{column}]))
VAR AllCount = COUNTROWS(ALL({dimension}))
RETURN SWITCH(
    TRUE(),
    SelectedCount = 0, "No {noun}",
    SelectedCount = 1, {single},
    SelectedCount = AllCount, "All {noun}",
    "Multiple {noun}"
)"""


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
ALLOWED_MEASURE_CATEGORIES = {
    "display_logic",
    "formatting",
    "dynamic_title",
    "semantic_aggregation",
}


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

    # dbt owns eligible records/components; semantic measures aggregate those components.
    _validate_filter_coverage(model)
    _validate_relationships(model, tables)
    _validate_measures(model, tables)
    handoff = resolved_model_path.with_name("semantic_measures.dax")
    if resolved_model_path.resolve() == MODEL_PATH.resolve():
        if handoff.read_text(encoding="utf-8-sig") != dax_handoff(model):
            raise ValueError("DAX handoff does not match model measure definitions")

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

        for endpoint in ("from", "to"):
            endpoint_table, endpoint_column = relationship[endpoint].split(
                ".", maxsplit=1
            )
            if (
                endpoint_table not in tables
                or endpoint_column not in tables[endpoint_table]["required_columns"]
            ):
                raise ValueError(
                    f"Relationship endpoint is undeclared: {relationship[endpoint]}"
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


def _validate_measures(model: dict, tables: dict[str, dict]) -> None:
    """Validate real DAX columns, measure dependencies and allowed aggregation."""
    measures = model.get("measures", [])
    names = {measure["name"] for measure in measures}
    if len(names) != len(measures):
        raise ValueError("Duplicate Power BI measure name")
    required_semantic = {
        "Approval Dollars",
        "Approval Records",
        "Average Approval Size",
        "Approval Amount Coverage",
        "Known 504 Third Party to SBA Amount Ratio",
        "504 Paired Financing Coverage",
        "7a Guarantee Rate",
        "7a Paired Guarantee Coverage",
        "Program Dollar Share",
        "Known Industry Dollar Share",
        "Industry Dollar Coverage",
        "Selected Top Five Known Lender Share",
        "Lender Dollar Coverage",
        "Approvals per 1000 Establishment Years",
        "Approval Dollars per Establishment Year",
        "Comparable Full Year Dollar Growth",
        "Selected Known Source Name Count",
        "State Mean Monthly SA Unemployment Rate",
        "State Unemployment Change PP",
    }
    if required_semantic - names:
        raise ValueError(
            "Missing required semantic measures: "
            + ", ".join(sorted(required_semantic - names))
        )
    if any(
        m["category"] != "semantic_aggregation"
        for m in measures
        if m["name"] in required_semantic
    ):
        raise ValueError(
            "Required semantic measures must use allowed component aggregation"
        )
    dependencies = {}
    for measure in measures:
        description = measure.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Empty Power BI measure description: {measure['name']}")
        category = measure.get("category")
        if category not in ALLOWED_MEASURE_CATEGORIES:
            raise ValueError(f"Power BI measure category is not allowed: {category}")
        expression = measure.get("expression", "")
        if not expression.strip():
            raise ValueError("Empty Power BI measure expression")
        references = re.findall(
            r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))\s*\[([^]]+)\]", expression
        )
        for quoted, bare, column in references:
            table = quoted or bare
            if table not in tables:
                raise ValueError(
                    f"Power BI measure references undeclared tables: {table}"
                )
            if column not in tables[table]["required_columns"]:
                raise ValueError(
                    f"Power BI measure references undeclared column: {table}[{column}]"
                )
        # Remove table-qualified columns before reading measure-only dependencies.
        without_columns = re.sub(
            r"(?:'[^']+'|[A-Za-z_][A-Za-z0-9_]*)\s*\[[^]]+\]", "", expression
        )
        deps = set(re.findall(r"\[([^]]+)\]", without_columns))
        if measure.get("aggregation") == "selected_top5":
            deps.discard(
                "__Amount"
            )  # scoped virtual column in the approved TOPN pattern
        if deps - names:
            raise ValueError(
                "Power BI measure references undeclared measure: "
                + ", ".join(sorted(deps - names))
            )
        dependencies[measure["name"]] = deps
        if category == "semantic_aggregation":
            expected = aggregation_expression(measure)
            if re.sub(r"\s+", "", expression) != re.sub(r"\s+", "", expected):
                raise ValueError("Power BI measure violates its allowed aggregation")
            # Includes table-only references in REMOVEFILTERS/SUMMARIZE/COUNTROWS.
            declared_tables = {measure["table"]}
            declared_tables.update(
                measure[key]
                for key in ("dimension", "denominator_table")
                if key in measure
            )
            if declared_tables - set(tables):
                raise ValueError("Semantic aggregation references undeclared table")
        else:
            if measure["name"] in {"Selected Year Label", "Selected State Label"}:
                expected = selection_label_expression(measure["name"])
                if re.sub(r"\s+", "", expression) != re.sub(r"\s+", "", expected):
                    raise ValueError(
                        "Selection label must distinguish empty, one, all and multiple subsets"
                    )
                continue
            functions = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression))
            if functions - {"COALESCE", "SELECTEDVALUE", "FORMAT"}:
                raise ValueError("Display measures may only format/select labels")

    def visit(name: str, path: set[str]) -> None:
        if name in path:
            raise ValueError("Cyclic Power BI measure dependency")
        for dependency in dependencies[name]:
            visit(dependency, path | {name})

    for name in names:
        visit(name, set())
