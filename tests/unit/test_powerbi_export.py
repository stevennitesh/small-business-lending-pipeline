from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from scripts.export_powerbi_tables import (
    BI_EXPORT_TABLES,
    PROHIBITED_EXPORT_FIELDS,
    REQUIRED_EXPORT_COLUMNS,
    export_powerbi_tables,
)


def test_export_powerbi_tables_writes_required_csvs(tmp_path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    export_dir = tmp_path / "powerbi"
    _create_bi_fixture_warehouse(duckdb_path)

    summary = export_powerbi_tables(
        duckdb_path=duckdb_path,
        export_dir=export_dir,
    )

    assert set(summary.row_counts) == set(BI_EXPORT_TABLES)
    assert all(row_count > 0 for row_count in summary.row_counts.values())

    for table_name in BI_EXPORT_TABLES:
        export_path = export_dir / f"{table_name}.csv"
        assert export_path.is_file()
        with export_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        assert rows
        assert REQUIRED_EXPORT_COLUMNS[table_name] <= set(reader.fieldnames or [])
        assert not (PROHIBITED_EXPORT_FIELDS & set(reader.fieldnames or []))


def test_export_powerbi_tables_writes_canonical_dimension_csvs(tmp_path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    export_dir = tmp_path / "powerbi"
    _create_bi_fixture_warehouse(duckdb_path)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            create or replace table dim_naics as
            select
                '31-33' as naics_key,
                '31-33' as naics_sector_code,
                'Manufacturing' as naics_sector_name,
                'Manufacturing sector' as naics_description,
                true as is_valid_current_code,
                false as is_unknown
            union all
            select
                '44-45' as naics_key,
                '44-45' as naics_sector_code,
                'Retail Trade' as naics_sector_name,
                'Retail trade sector' as naics_description,
                true as is_valid_current_code,
                false as is_unknown
            """
        )

    export_powerbi_tables(
        duckdb_path=duckdb_path,
        export_dir=export_dir,
    )

    with (export_dir / "dim_naics.csv").open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert {row["naics_key"] for row in rows} == {"31-33", "44-45"}
    assert len(rows) == len({row["naics_key"] for row in rows})


def test_export_powerbi_tables_rejects_empty_or_unsafe_exports(tmp_path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    _create_bi_fixture_warehouse(duckdb_path)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute(
            """
            create or replace table bi_executive_overview as
            select * from bi_executive_overview where false
            """
        )

    with pytest.raises(ValueError, match="has no rows"):
        export_powerbi_tables(
            duckdb_path=duckdb_path,
            export_dir=tmp_path / "powerbi",
        )

    _create_bi_fixture_warehouse(duckdb_path)
    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute("alter table bi_program_mix add column borrower_name varchar")

    with pytest.raises(ValueError, match="prohibited fields"):
        export_powerbi_tables(
            duckdb_path=duckdb_path,
            export_dir=tmp_path / "powerbi",
        )


def _create_bi_fixture_warehouse(duckdb_path: Path) -> None:
    with duckdb.connect(str(duckdb_path)) as connection:
        for table_name, required_columns in REQUIRED_EXPORT_COLUMNS.items():
            select_list = [
                _fixture_expression(column_name)
                for column_name in sorted(required_columns)
            ]
            connection.execute(
                f"create or replace table {table_name} as select "
                + ", ".join(select_list)
            )


def _fixture_expression(column_name: str) -> str:
    if column_name.endswith("_count") or column_name in {
        "loan_count",
        "lender_count",
        "source_resource_count",
        "failed_check_count",
        "warning_check_count",
        "passed_check_count",
    }:
        return f"1 as {column_name}"
    if column_name.endswith("_amount") or column_name.endswith("_share"):
        return f"1.0 as {column_name}"
    if column_name.endswith("_status"):
        return f"'passed' as {column_name}"
    if column_name.endswith("_year") or column_name == "year":
        return f"2026 as {column_name}"
    return f"'fixture' as {column_name}"
