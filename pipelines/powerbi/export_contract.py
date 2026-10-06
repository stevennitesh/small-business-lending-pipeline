from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb

from pipelines.powerbi.export_schema import (
    BI_EXPORT_TABLES,
    PROHIBITED_EXPORT_FIELDS,
    REQUIRED_EXPORT_COLUMNS,
)


_SAFE_TABLE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PowerBIExportSummary:
    """Summary of local CSV exports for the Power BI dashboard."""

    duckdb_path: str
    export_dir: str
    export_paths: dict[str, str]
    row_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the export summary for flow output or CLI JSON."""
        return asdict(self)


def export_powerbi_tables(
    *,
    duckdb_path: Path | str = "data/warehouse/small_business_lending.duckdb",
    export_dir: Path | str = "data/exports/powerbi",
) -> PowerBIExportSummary:
    """Validate BI tables and export the Power BI CSV contract."""
    resolved_duckdb_path = Path(duckdb_path)
    if not resolved_duckdb_path.is_file():
        raise FileNotFoundError(f"DuckDB warehouse not found: {resolved_duckdb_path}")

    resolved_export_dir = Path(export_dir)
    resolved_export_dir.mkdir(parents=True, exist_ok=True)

    export_paths: dict[str, str] = {}
    with duckdb.connect(str(resolved_duckdb_path)) as connection:
        row_counts = validate_powerbi_export_tables(connection)
        # Finish every COPY before replacing the previous export set. Staging and
        # rollback backups exist only for this call, on the same filesystem.
        with TemporaryDirectory(
            prefix=".powerbi-export-", dir=resolved_export_dir
        ) as temporary:
            staging = Path(temporary)
            for table_name in BI_EXPORT_TABLES:
                safe_table_name = _validate_table_identifier(table_name)
                connection.execute(
                    f"copy (select * from {safe_table_name}) to ? (header, delimiter ',')",
                    [str(staging / f"{table_name}.csv")],
                )
            _publish_csv_exports(staging, resolved_export_dir)
        export_paths = {
            name: str(resolved_export_dir / f"{name}.csv") for name in BI_EXPORT_TABLES
        }

    return PowerBIExportSummary(
        duckdb_path=str(resolved_duckdb_path),
        export_dir=str(resolved_export_dir),
        export_paths=export_paths,
        row_counts=row_counts,
    )


def validate_powerbi_export_tables(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    """Validate every BI export table and return non-empty row counts."""
    row_counts: dict[str, int] = {}
    for table_name in BI_EXPORT_TABLES:
        validate_powerbi_table_contract(connection, table_name)
        row_count = _row_count(connection, table_name)
        if row_count <= 0:
            raise ValueError(f"BI export table {table_name} has no rows.")
        row_counts[table_name] = row_count
    return row_counts


def validate_powerbi_table_contract(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> None:
    """Validate one DuckDB BI table against the Power BI export contract."""
    safe_table_name = _validate_table_identifier(table_name)
    columns = _columns(connection, safe_table_name)
    if not columns:
        raise ValueError(f"BI export table {safe_table_name} does not exist.")

    validate_powerbi_export_columns(safe_table_name, columns)


def validate_powerbi_export_columns(
    table_name: str, columns: set[str], *, case_insensitive: bool = False
) -> None:
    """Enforce the same modeled source boundary for local and cloud tables."""
    safe_table_name = _validate_table_identifier(table_name)
    required_columns = (
        {column.lower() for column in columns} if case_insensitive else columns
    )
    missing_columns = sorted(
        REQUIRED_EXPORT_COLUMNS[safe_table_name] - required_columns
    )
    if missing_columns:
        raise ValueError(
            f"BI export table {safe_table_name} is missing required columns: "
            + ", ".join(missing_columns)
        )

    prohibited_columns = sorted(
        PROHIBITED_EXPORT_FIELDS & {column.lower() for column in columns}
    )
    if prohibited_columns:
        raise ValueError(
            f"BI export table {safe_table_name} includes prohibited fields: "
            + ", ".join(prohibited_columns)
        )


LEGACY_EXPORT_TABLES = {
    "dim_date",
    "dim_state",
    "dim_lender",
    "dim_naics",
    "dim_loan_program",
    "dim_source_file",
}


def _publish_csv_exports(staging: Path, export_dir: Path) -> None:
    """Publish a complete set, restoring the previous set on a rename failure."""
    names = set(BI_EXPORT_TABLES) | LEGACY_EXPORT_TABLES
    destinations = [export_dir / f"{name}.csv" for name in sorted(names)]
    for path in destinations:
        if path.exists() and not path.is_file():
            raise ValueError(f"Export destination is not a file: {path}")
    backup = staging / "previous"
    backup.mkdir()
    moved = []
    published = []
    try:
        for path in destinations:
            if path.exists():
                path.replace(backup / path.name)
                moved.append(path)
        for name in BI_EXPORT_TABLES:
            destination = export_dir / f"{name}.csv"
            (staging / destination.name).replace(destination)
            published.append(destination)
    except Exception:
        for path in published:
            path.unlink()
        for path in moved:
            (backup / path.name).replace(path)
        raise


def _columns(connection: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    """Return DuckDB column names for a BI table in the main schema."""
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
    """Return the row count for a validated BI export table."""
    safe_table_name = _validate_table_identifier(table_name)
    return int(
        connection.execute(f"select count(*) from {safe_table_name}").fetchone()[0]
    )


def _validate_table_identifier(table_name: str) -> str:
    """Require a known BI table name before interpolating SQL identifiers."""
    # DuckDB cannot bind table identifiers as parameters, so export SQL only
    # interpolates names that are both contract-listed and identifier-shaped.
    if table_name not in BI_EXPORT_TABLES or not _SAFE_TABLE_IDENTIFIER.fullmatch(
        table_name
    ):
        raise ValueError(f"Invalid BI export table identifier: {table_name}")
    return table_name
