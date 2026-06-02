from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.powerbi.export_contract import export_powerbi_tables  # noqa: E402


def main() -> None:
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
