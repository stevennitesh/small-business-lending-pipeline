from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb


BI_EXPORT_TABLES = (
    "bi_executive_overview",
    "bi_state_lending_trends",
    "bi_lender_concentration",
    "bi_industry_mix",
    "bi_program_mix",
    "bi_regional_business_health",
    "bi_pipeline_health",
    "bi_lender_mix",
    "bi_lending_performance",
    "bi_lending_status_mix",
    "bi_lending_terms_pricing",
    "bi_lending_jobs_impact",
    "bi_state_filter",
    "bi_year_filter",
    "bi_loan_program_filter",
    "bi_naics_filter",
    "bi_lender_filter",
)

REQUIRED_EXPORT_COLUMNS = {
    "bi_executive_overview": {
        "state_key",
        "state_name",
        "year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "annual_average_unemployment_rate",
        "establishment_count",
        "loans_per_1000_establishments",
        "approved_loan_dollars_per_establishment",
        "context_join_status",
    },
    "bi_state_lending_trends": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "approved_loan_amount_yoy_growth_pct",
    },
    "bi_lender_concentration": {
        "state_key",
        "state_name",
        "approval_year",
        "top_5_lender_share",
        "lender_count",
    },
    "bi_industry_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "naics_key",
        "industry_approved_amount_share",
    },
    "bi_program_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "loan_program_key",
        "program_approved_amount_share",
    },
    "bi_regional_business_health": {
        "state_key",
        "state_name",
        "year",
        "annual_average_unemployment_rate",
        "unemployment_rate_yoy_change_pct",
        "establishment_count",
        "establishment_entry_rate",
        "establishment_exit_rate",
        "loans_per_1000_establishments",
        "approved_loan_dollars_per_establishment",
        "context_join_status",
    },
    "bi_pipeline_health": {
        "latest_run_status",
        "validation_status",
        "freshness_status",
    },
    "bi_lender_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "lender_key",
        "lender_name",
        "total_approved_loan_amount",
        "loan_count",
        "lender_approved_amount_share",
        "lender_rank",
    },
    "bi_lending_performance": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "gross_chargeoff_amount",
        "charged_off_loan_count",
        "chargeoff_amount_rate",
        "charged_off_loan_count_rate",
    },
    "bi_lending_status_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "loan_status_group",
        "loan_status_group_label",
        "loan_status_sort_order",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "gross_chargeoff_amount",
        "charged_off_loan_count",
        "status_group_approved_amount_share",
        "status_group_loan_count_share",
    },
    "bi_lending_terms_pricing": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "term_coverage_count",
        "term_coverage_rate",
        "average_term_months",
        "initial_interest_rate_coverage_count",
        "initial_interest_rate_coverage_rate",
        "average_initial_interest_rate",
        "interest_type_coverage_count",
        "fixed_interest_loan_count",
        "variable_interest_loan_count",
        "fixed_interest_loan_share",
        "variable_interest_loan_share",
        "seven_a_approved_loan_amount",
        "sba_guaranteed_approval_amount",
        "seven_a_sba_guarantee_rate",
        "third_party_dollars",
        "third_party_to_approved_amount_rate",
    },
    "bi_lending_jobs_impact": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "jobs_supported_coverage_count",
        "jobs_supported_coverage_rate",
        "total_jobs_supported",
        "jobs_supported_per_loan",
        "jobs_supported_per_1m_approved",
        "approved_loan_dollars_per_job_supported",
    },
    "bi_state_filter": {
        "state_key",
        "state_fips",
        "state_abbr",
        "state_name",
        "census_region",
        "census_division",
    },
    "bi_year_filter": {
        "year",
        "year_label",
    },
    "bi_loan_program_filter": {
        "loan_program_key",
        "loan_program",
        "loan_program_name",
    },
    "bi_naics_filter": {
        "naics_key",
        "naics_sector_code",
        "naics_sector_name",
        "naics_description",
        "is_valid_current_code",
        "is_unknown",
    },
    "bi_lender_filter": {
        "lender_key",
        "lender_name",
        "is_unknown",
    },
}

PROHIBITED_EXPORT_FIELDS = {
    "borrower_name",
    "borrower_city",
    "borrower_zip",
    "raw_file_path",
    "source_loan_id",
}


@dataclass(frozen=True)
class PowerBIExportSummary:
    duckdb_path: str
    export_dir: str
    export_paths: dict[str, str]
    row_counts: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def export_powerbi_tables(
    *,
    duckdb_path: Path | str = "data/warehouse/small_business_lending.duckdb",
    export_dir: Path | str = "data/exports/powerbi",
) -> PowerBIExportSummary:
    resolved_duckdb_path = Path(duckdb_path)
    if not resolved_duckdb_path.is_file():
        raise FileNotFoundError(f"DuckDB warehouse not found: {resolved_duckdb_path}")

    resolved_export_dir = Path(export_dir)
    resolved_export_dir.mkdir(parents=True, exist_ok=True)

    export_paths: dict[str, str] = {}
    with duckdb.connect(str(resolved_duckdb_path)) as connection:
        row_counts = _validate_powerbi_export_tables(connection)
        _remove_stale_csv_exports(resolved_export_dir)

        for table_name in BI_EXPORT_TABLES:
            export_path = resolved_export_dir / f"{table_name}.csv"
            connection.execute(
                f"copy (select * from {table_name}) to ? (header, delimiter ',')",
                [str(export_path)],
            )
            export_paths[table_name] = str(export_path)

    return PowerBIExportSummary(
        duckdb_path=str(resolved_duckdb_path),
        export_dir=str(resolved_export_dir),
        export_paths=export_paths,
        row_counts=row_counts,
    )


def _validate_powerbi_export_tables(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    row_counts: dict[str, int] = {}
    for table_name in BI_EXPORT_TABLES:
        validate_powerbi_table_contract(connection, table_name)
        row_count = _row_count(connection, table_name)
        if row_count <= 0:
            raise ValueError(f"BI export table {table_name} has no rows.")
        row_counts[table_name] = row_count
    return row_counts


def _remove_stale_csv_exports(export_dir: Path) -> None:
    expected_table_names = set(BI_EXPORT_TABLES)
    for export_path in export_dir.glob("*.csv"):
        if export_path.is_file() and export_path.stem not in expected_table_names:
            export_path.unlink()


def validate_powerbi_table_contract(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> None:
    columns = _columns(connection, table_name)
    if not columns:
        raise ValueError(f"BI export table {table_name} does not exist.")

    missing_columns = sorted(REQUIRED_EXPORT_COLUMNS[table_name] - columns)
    if missing_columns:
        raise ValueError(
            f"BI export table {table_name} is missing required columns: "
            + ", ".join(missing_columns)
        )

    prohibited_columns = sorted(PROHIBITED_EXPORT_FIELDS & columns)
    if prohibited_columns:
        raise ValueError(
            f"BI export table {table_name} includes prohibited fields: "
            + ", ".join(prohibited_columns)
        )


def _columns(connection: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'main'
              and table_name = ?
            """,
            [table_name],
        ).fetchall()
    }


def _row_count(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    return int(connection.execute(f"select count(*) from {table_name}").fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Export BI tables as local Power BI CSV files.")
    parser.add_argument(
        "--duckdb-path",
        default="data/warehouse/small_business_lending.duckdb",
    )
    parser.add_argument("--export-dir", default="data/exports/powerbi")
    args = parser.parse_args()

    summary = export_powerbi_tables(
        duckdb_path=args.duckdb_path,
        export_dir=args.export_dir,
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
