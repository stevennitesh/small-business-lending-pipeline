from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

from pipelines.powerbi.export_schema import (
    BI_EXPORT_TABLES,
    PROHIBITED_EXPORT_FIELDS,
    REQUIRED_EXPORT_COLUMNS,
)


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
        row_counts = validate_powerbi_export_tables(connection)
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


def validate_powerbi_export_tables(
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
