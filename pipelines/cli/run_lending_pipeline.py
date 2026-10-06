from __future__ import annotations

import argparse
import os

from pipelines.flows.lending_pipeline_flow import lending_pipeline_flow


def build_parser() -> argparse.ArgumentParser:
    """Build the local lending pipeline command-line parser."""
    parser = argparse.ArgumentParser(description="Run the local lending pipeline flow.")
    parser.add_argument("--run-mode", default="local")
    parser.add_argument(
        "--extract-mode",
        choices=("fixture", "live"),
        default=os.getenv("SOURCE_EXTRACT_MODE", "fixture"),
    )
    parser.add_argument("--dbt-target", default="dev_duckdb")
    parser.add_argument("--data-root", default="data")
    parser.add_argument(
        "--duckdb-path",
        default="data/warehouse/small_business_lending.duckdb",
    )
    parser.add_argument("--dbt-project-dir", default="dbt")
    parser.add_argument("--dbt-profiles-dir", default=".tmp/dbt_profiles")
    parser.add_argument("--powerbi-export-dir")
    parser.add_argument("--s3-bucket")
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--source-start-year", type=int)
    parser.add_argument("--source-end-year", type=int)
    return parser


def main() -> None:
    """Parse CLI arguments and run the local lending pipeline flow."""
    args = build_parser().parse_args()
    summary_path = lending_pipeline_flow(
        run_mode=args.run_mode,
        extract_mode=args.extract_mode,
        dbt_target=args.dbt_target,
        data_root=args.data_root,
        duckdb_path=args.duckdb_path,
        dbt_project_dir=args.dbt_project_dir,
        dbt_profiles_dir=args.dbt_profiles_dir,
        powerbi_export_dir=args.powerbi_export_dir,
        s3_bucket=args.s3_bucket,
        pipeline_run_id=args.pipeline_run_id,
        source_start_year=args.source_start_year,
        source_end_year=args.source_end_year,
    )
    print(summary_path)


if __name__ == "__main__":
    main()
