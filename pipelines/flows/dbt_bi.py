"""Flow adapters for dbt execution, BI validation, exports, and cloud artifacts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import duckdb
from dotenv import load_dotenv

from pipelines.flows.extraction_manifests import ExtractionPaths
from pipelines.flows.run_models import DbtBuildResult, LocalRunContext
from pipelines.flows.run_setup import resolve_s3_bucket
from pipelines.load.s3_loader import (
    S3UploadSummary,
    build_dbt_artifact_upload_item,
    upload_items_to_s3,
)
from pipelines.load.snowflake_loader import SnowflakeConfig, connect_to_snowflake
from scripts.export_powerbi_tables import (
    BI_EXPORT_TABLES,
    export_powerbi_tables,
    validate_powerbi_export_tables,
)


BI_TABLES = BI_EXPORT_TABLES
BucketResolver = Callable[[LocalRunContext], str | None]
_SNOWFLAKE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def run_dbt_build_for_context(context: LocalRunContext) -> DbtBuildResult:
    """Run `dbt build` for the active context and return captured output."""
    load_dotenv(override=False)
    ensure_dbt_profile(context)
    dbt_executable = dbt_executable_path()
    command = (
        str(dbt_executable),
        "build",
        "--target",
        context.dbt_target,
    )
    completed = subprocess.run(
        command,
        cwd=context.dbt_project_dir,
        env={
            **dict(os.environ),
            "DBT_PROFILES_DIR": str(context.dbt_profiles_dir.resolve()),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    result = DbtBuildResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "dbt build failed with exit code "
            f"{completed.returncode}\n{completed.stdout}\n{completed.stderr}"
        )
    return result


def collect_dbt_artifacts_for_context(context: LocalRunContext) -> dict[str, str]:
    """Collect required dbt target artifacts after a successful build."""
    target_dir = context.dbt_project_dir / "target"
    artifacts = {
        name: str(target_dir / name)
        for name in ("manifest.json", "run_results.json")
        if (target_dir / name).is_file()
    }
    if not artifacts:
        raise RuntimeError("dbt build did not produce target artifacts.")
    return artifacts


def upload_dbt_artifacts_for_context(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    dbt_artifacts: dict[str, str],
    *,
    s3_bucket_resolver: BucketResolver | None = None,
) -> S3UploadSummary:
    """Upload dbt artifacts to S3 using the run manifest partition metadata."""
    bucket = (s3_bucket_resolver or resolve_s3_bucket)(context)
    if not dbt_artifacts:
        return S3UploadSummary(bucket=bucket, uploaded_objects=())

    first_manifest = json.loads(
        extraction_paths.manifest_paths[0].read_text(encoding="utf-8")
    )
    items = [
        build_dbt_artifact_upload_item(
            artifact_path,
            ingestion_date=str(first_manifest["ingestion_date"]),
            pipeline_run_id=str(first_manifest["pipeline_run_id"]),
        )
        for artifact_path in dbt_artifacts.values()
    ]
    return upload_items_to_s3(
        items,
        bucket=bucket,
        required=context.is_cloud_route,
    )


def validate_bi_tables_for_context(context: LocalRunContext) -> dict[str, int]:
    """Validate BI table row counts in DuckDB or Snowflake."""
    if context.is_cloud_route:
        return validate_snowflake_bi_tables()

    with duckdb.connect(str(context.duckdb_path)) as connection:
        return validate_powerbi_export_tables(connection)


def export_bi_tables_for_context(context: LocalRunContext) -> list[str]:
    """Export local BI tables to files for Power BI."""
    summary = export_powerbi_tables(
        duckdb_path=context.duckdb_path,
        export_dir=context.run_export_dir,
    )
    return [summary.export_paths[table_name] for table_name in BI_TABLES]


def ensure_dbt_profile(context: LocalRunContext) -> None:
    """Create the dbt profile needed for the active local or cloud target."""
    context.dbt_profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_path = context.dbt_profiles_dir / "profiles.yml"
    if context.is_cloud_route or context.dbt_target == "prod_snowflake":
        example_profile = context.dbt_project_dir / "profiles.yml.example"
        shutil.copyfile(example_profile, profile_path)
        return

    profile_path.write_text(
        f"""small_business_lending_pipeline:
  target: {context.dbt_target}
  outputs:
    {context.dbt_target}:
      type: duckdb
      path: {context.duckdb_path.resolve()}
      threads: 1
""",
        encoding="utf-8",
    )


def dbt_executable_path() -> Path:
    """Prefer the current virtualenv's dbt executable, falling back to PATH."""
    executable = Path(sys.executable).with_name("dbt")
    if executable.is_file():
        return executable
    return Path("dbt")


def validate_snowflake_bi_tables() -> dict[str, int]:
    """Validate configured Snowflake BI tables and return row counts."""
    config = SnowflakeConfig.from_env()
    bi_schema = snowflake_bi_schema()
    quoted_bi_schema = quote_snowflake_identifier(bi_schema)
    connection = connect_to_snowflake(config)
    try:
        row_counts: dict[str, int] = {}
        with connection.cursor() as cursor:
            for table_name in BI_TABLES:
                quoted_table_name = quote_snowflake_identifier(table_name.upper())
                cursor.execute(
                    f"select count(*) from {quoted_bi_schema}.{quoted_table_name}"
                )
                row_count = int(cursor.fetchone()[0])
                if row_count <= 0:
                    raise RuntimeError(
                        f"BI table {bi_schema}.{table_name.upper()} has no rows."
                    )
                row_counts[table_name] = row_count
        return row_counts
    finally:
        connection.close()


def quote_snowflake_identifier(identifier: str) -> str:
    """Quote a safe Snowflake identifier after strict validation."""
    if not _SNOWFLAKE_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Invalid Snowflake identifier: {identifier}")
    return f'"{identifier.upper()}"'


def snowflake_bi_schema() -> str:
    """Resolve the Snowflake BI schema from explicit env or dbt schema prefix."""
    load_dotenv(override=False)
    schema_prefix = os.getenv("DBT_SCHEMA_PREFIX", "").strip()
    return os.getenv("SNOWFLAKE_BI_SCHEMA") or (
        f"{schema_prefix}_BI" if schema_prefix else "BI"
    )
