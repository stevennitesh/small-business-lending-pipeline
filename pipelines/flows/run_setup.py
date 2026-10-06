"""Run-context setup and environment checks for pipeline flows."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from pipelines.flows.run_models import (
    LocalRunContext,
    VALID_EXTRACT_MODES,
    VALID_RUN_MODES,
)
from pipelines.load.snowflake_loader import SnowflakeConfig
from pipelines.utils.dates import utc_now_iso


def initialize_run_context(
    *,
    run_mode: str,
    extract_mode: str,
    dbt_target: str,
    data_root: str,
    duckdb_path: str,
    dbt_project_dir: str,
    dbt_profiles_dir: str,
    powerbi_export_dir: str | None = None,
    s3_bucket: str | None = None,
    pipeline_run_id: str | None = None,
    source_start_year: int | None = None,
    source_end_year: int | None = None,
) -> LocalRunContext:
    """Normalize runtime inputs, create a run context, and prepare directories."""
    normalized_run_mode = normalize_run_mode(run_mode)
    expected_target = (
        "prod_snowflake" if normalized_run_mode == "cloud" else "dev_duckdb"
    )
    if dbt_target != expected_target:
        raise ValueError(
            f"run_mode={normalized_run_mode} requires dbt_target={expected_target}"
        )
    if extract_mode not in VALID_EXTRACT_MODES:
        raise ValueError("extract_mode must be 'fixture' or 'live'.")
    if source_start_year and source_end_year and source_start_year > source_end_year:
        raise ValueError("source_start_year cannot be greater than source_end_year.")

    run_id = pipeline_run_id or f"{normalized_run_mode}-{uuid.uuid4()}"
    resolved_data_root = Path(data_root)
    context = LocalRunContext(
        pipeline_run_id=run_id,
        run_mode=normalized_run_mode,
        extract_mode=extract_mode,
        data_root=resolved_data_root,
        duckdb_path=Path(duckdb_path),
        dbt_project_dir=Path(dbt_project_dir),
        dbt_profiles_dir=Path(dbt_profiles_dir),
        dbt_target=dbt_target,
        powerbi_export_dir=resolve_powerbi_export_dir(
            resolved_data_root,
            powerbi_export_dir,
        ),
        run_started_at_utc=utc_now_iso(),
        s3_bucket=s3_bucket,
        source_start_year=source_start_year,
        source_end_year=source_end_year,
    )
    if context.run_validation_dir.exists() and any(
        context.run_validation_dir.iterdir()
    ):
        raise FileExistsError(
            f"Run evidence already exists; use a fresh pipeline_run_id: {run_id}"
        )
    if (
        extract_mode == "fixture"
        and not context.is_cloud_route
        and context.duckdb_path.is_file()
    ):
        with duckdb.connect(str(context.duckdb_path), read_only=True) as connection:
            try:
                non_fixture = connection.execute(
                    "select count(*) from raw.raw_ingestion_manifest where source_url is null or source_url not like 'fixture://%'"
                ).fetchone()[0]
            except duckdb.Error as exc:
                raise ValueError(
                    "Existing warehouse is not a verified fixture destination; use an isolated --duckdb-path"
                ) from exc
            if non_fixture:
                raise ValueError(
                    "Fixture mode cannot replace a live warehouse; use an isolated --duckdb-path"
                )
    create_context_directories(context)
    return context


def create_context_directories(context: LocalRunContext) -> None:
    """Create local directories required before flow stages write artifacts."""
    context.data_root.mkdir(parents=True, exist_ok=True)
    context.run_validation_dir.mkdir(parents=True, exist_ok=True)
    context.run_export_dir.mkdir(parents=True, exist_ok=True)


def require_cloud_mode_config_for_context(context: LocalRunContext) -> str:
    """Validate cloud-mode environment and return the resolved S3 bucket."""
    if not context.is_cloud_route:
        return context.s3_bucket or ""

    load_dotenv(override=False)
    bucket = resolve_s3_bucket(context)
    missing = []
    if not bucket:
        missing.append("S3_BUCKET")
    try:
        snowflake_config = SnowflakeConfig.from_env()
    except Exception as exc:
        snowflake_config = None
        missing.append(f"SNOWFLAKE_CONFIG: {exc}")
    if snowflake_config is not None and not snowflake_config.storage_integration:
        missing.append("SNOWFLAKE_STORAGE_INTEGRATION")
    if missing:
        raise RuntimeError(
            "Missing cloud mode configuration: " + ", ".join(sorted(missing))
        )
    return bucket


def resolve_s3_bucket(context: LocalRunContext) -> str | None:
    """Resolve the S3 bucket from explicit context first, then environment."""
    return context.s3_bucket or os.getenv("S3_BUCKET") or None


def normalize_run_mode(run_mode: str) -> str:
    """Validate the accepted run modes."""
    if run_mode in VALID_RUN_MODES:
        return run_mode
    allowed = ", ".join(VALID_RUN_MODES)
    raise ValueError(f"run_mode must be one of: {allowed}")


def resolve_powerbi_export_dir(data_root: Path, configured_dir: str | None) -> Path:
    """Resolve Power BI export directory from explicit input, env, or data root."""
    configured = configured_dir or os.getenv("POWERBI_EXPORT_DIR")
    if configured:
        return Path(configured)
    return data_root / "exports" / "powerbi"
