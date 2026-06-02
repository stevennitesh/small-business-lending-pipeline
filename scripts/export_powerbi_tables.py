from __future__ import annotations

import argparse
import json

try:
    from scripts.repo_bootstrap import add_repo_root_to_path
except ModuleNotFoundError:
    from repo_bootstrap import add_repo_root_to_path

add_repo_root_to_path()

from pipelines.powerbi.export_contract import export_powerbi_tables


def main() -> None:
    """Export local DuckDB BI tables as Power BI CSVs."""
    parser = argparse.ArgumentParser(
        description="Export BI tables as local Power BI CSV files.",
    )
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
