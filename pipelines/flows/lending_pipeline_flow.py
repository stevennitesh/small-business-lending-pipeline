"""Prefect orchestration for the local-first lending pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task

from pipelines.flows import (
    dbt_bi,
    fixture_source_extracts,
    raw_loads,
    raw_validation,
    run_setup,
    run_summary,
    source_extracts,
)
from pipelines.flows.run_models import (
    DbtBuildResult,
    FlowRunState,
    LocalRunContext,
    VALID_RUN_MODES,
)
from pipelines.flows.stage_execution import run_timed_flow_stage
from pipelines.flows.extraction_manifests import ExtractionPaths
from pipelines.flows.raw_loads import (
    RawLoadSummary,
    S3UploadSummary,
    SnowflakeRawLoadSummary,
)
from pipelines.utils.config import ProjectConfig, load_project_config
from pipelines.validation.raw_validation_models import RawValidationOutput


@task
def initialize_run(
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
    """Create a run context and prepare local run directories."""
    return run_setup.initialize_run_context(
        run_mode=run_mode,
        extract_mode=extract_mode,
        dbt_target=dbt_target,
        data_root=data_root,
        duckdb_path=duckdb_path,
        dbt_project_dir=dbt_project_dir,
        dbt_profiles_dir=dbt_profiles_dir,
        powerbi_export_dir=powerbi_export_dir,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        source_start_year=source_start_year,
        source_end_year=source_end_year,
    )


@task
def load_config(config_dir: str = "config") -> ProjectConfig:
    """Load project configuration for source, validation, and runtime settings."""
    return load_project_config(Path(config_dir))


@task
def require_cloud_mode_config(context: LocalRunContext) -> str:
    """Fail early when cloud mode lacks required S3 or Snowflake settings."""
    return run_setup.require_cloud_mode_config_for_context(context)


@task
def extract_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
) -> ExtractionPaths:
    """Run fixture or live source extraction and return manifest references."""
    if context.run_mode not in VALID_RUN_MODES:
        allowed = ", ".join(f"'{mode}'" for mode in VALID_RUN_MODES)
        raise ValueError(
            f"run_mode must be one of {allowed}; got {context.run_mode!r}."
        )
    if context.extract_mode == "live":
        return source_extracts.extract_live_sources(context, project_config)
    return fixture_source_extracts.extract_fixture_sources_for_flow(
        context,
        project_config,
    )


@task
def validate_raw_outputs(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    project_config: ProjectConfig,
) -> RawValidationOutput:
    """Validate raw manifests, raw artifacts, and source payload contracts."""
    return raw_validation.validate_raw_outputs_for_flow(
        context,
        extraction_paths,
        project_config,
    )


@task
def load_duckdb_raw_tables(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_output: RawValidationOutput,
) -> RawLoadSummary:
    """Load validated raw artifacts into the local DuckDB warehouse."""
    return raw_loads.load_duckdb_raw_tables_for_context(
        context,
        extraction_paths,
        validation_output,
    )


@task
def record_raw_artifact_locations(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_output: RawValidationOutput,
) -> S3UploadSummary:
    """Record cloud raw artifact locations for summary reporting."""
    return raw_loads.record_raw_artifact_locations_for_context(
        context,
        extraction_paths,
        validation_output,
    )


@task
def load_snowflake_raw_tables(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_output: RawValidationOutput,
) -> SnowflakeRawLoadSummary:
    """Load validated raw artifacts into Snowflake for cloud runs."""
    return raw_loads.load_snowflake_raw_tables_for_context(
        context,
        extraction_paths,
        validation_output,
    )


@task
def run_dbt_build(context: LocalRunContext) -> DbtBuildResult:
    """Run dbt models for the active local or cloud target."""
    return dbt_bi.run_dbt_build_for_context(context)


@task
def collect_dbt_artifacts(context: LocalRunContext) -> dict[str, str]:
    """Collect dbt target artifacts produced by the build."""
    return dbt_bi.collect_dbt_artifacts_for_context(context)


@task
def upload_dbt_artifacts_to_s3(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    dbt_artifacts: dict[str, str],
) -> S3UploadSummary:
    """Upload dbt artifacts for cloud-run lineage."""
    return dbt_bi.upload_dbt_artifacts_for_context(
        context,
        extraction_paths,
        dbt_artifacts,
    )


@task
def validate_bi_tables(context: LocalRunContext) -> dict[str, int]:
    """Validate BI table row counts for the active dbt target."""
    return dbt_bi.validate_bi_tables_for_context(context)


@task
def export_bi_tables(context: LocalRunContext) -> list[str]:
    """Export local BI tables for Power BI consumption."""
    return dbt_bi.export_bi_tables_for_context(context)


@task
def write_run_summary(
    context: LocalRunContext,
    *,
    status: str,
    completed_stages: list[str],
    failed_stage: str | None = None,
    error_message: str | None = None,
    validation_result_path: Path | RawValidationOutput | None = None,
    manifest_artifact_uris: list[str] | None = None,
    dbt_artifacts: dict[str, str] | None = None,
    bi_row_counts: dict[str, int] | None = None,
    export_paths: list[str] | None = None,
    s3_upload_summary: dict[str, Any] | None = None,
    snowflake_raw_load_summary: dict[str, Any] | None = None,
    stage_durations_seconds: dict[str, float] | None = None,
) -> Path:
    """Write the durable run summary for success or failure states."""
    return run_summary.write_run_summary_for_context(
        context,
        status=status,
        completed_stages=completed_stages,
        failed_stage=failed_stage,
        error_message=error_message,
        validation_result_path=validation_result_path,
        manifest_artifact_uris=manifest_artifact_uris,
        dbt_artifacts=dbt_artifacts,
        bi_row_counts=bi_row_counts,
        export_paths=export_paths,
        s3_upload_summary=s3_upload_summary,
        snowflake_raw_load_summary=snowflake_raw_load_summary,
        stage_durations_seconds=stage_durations_seconds,
    )


@task
def write_state_run_summary(
    context: LocalRunContext,
    state: FlowRunState,
    *,
    status: str,
    failed_stage: str | None = None,
    error_message: str | None = None,
) -> Path:
    """Write the durable run summary from accumulated flow state."""
    return run_summary.write_state_run_summary_for_context(
        context,
        state,
        status=status,
        failed_stage=failed_stage,
        error_message=error_message,
    )


@flow(name="small-business-lending-local-pipeline")
def lending_pipeline_flow(
    *,
    run_mode: str = "local",
    extract_mode: str = "fixture",
    dbt_target: str = "dev_duckdb",
    data_root: str = "data",
    duckdb_path: str = "data/warehouse/small_business_lending.duckdb",
    dbt_project_dir: str = "dbt",
    dbt_profiles_dir: str = ".tmp/dbt_profiles",
    powerbi_export_dir: str | None = None,
    s3_bucket: str | None = None,
    pipeline_run_id: str | None = None,
    source_start_year: int | None = None,
    source_end_year: int | None = None,
) -> str:
    """Run the end-to-end lending pipeline and return the run summary path."""
    logger = get_run_logger()
    state = FlowRunState()
    context = initialize_run(
        run_mode=run_mode,
        extract_mode=extract_mode,
        dbt_target=dbt_target,
        data_root=data_root,
        duckdb_path=duckdb_path,
        dbt_project_dir=dbt_project_dir,
        dbt_profiles_dir=dbt_profiles_dir,
        powerbi_export_dir=powerbi_export_dir,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        source_start_year=source_start_year,
        source_end_year=source_end_year,
    )
    state.complete("initialize_run")

    try:
        project_config = load_config()
        state.complete("load_config")

        if context.is_cloud_route:
            require_cloud_mode_config(context)
            state.complete("require_cloud_mode_config")

        extraction_paths = run_timed_flow_stage(
            state,
            "extract_sources",
            extract_sources,
            context,
            project_config,
            completed_stages=("extract_sources", "write_manifests"),
        )
        state.manifest_artifact_uris = [
            location.artifact_uri for location in extraction_paths.manifest_locations
        ]

        state.validation_output = run_timed_flow_stage(
            state,
            "validate_raw_outputs",
            validate_raw_outputs,
            context,
            extraction_paths,
            project_config,
        )

        if context.is_cloud_route:
            raw_s3_summary = run_timed_flow_stage(
                state,
                "record_raw_artifact_locations",
                record_raw_artifact_locations,
                context,
                extraction_paths,
                state.validation_output,
            )
            state.s3_upload_summary["raw_artifacts"] = raw_s3_summary.to_dict()

            snowflake_summary = run_timed_flow_stage(
                state,
                "load_snowflake_raw_tables",
                load_snowflake_raw_tables,
                context,
                extraction_paths,
                state.validation_output,
            )
            state.snowflake_raw_load_summary = snowflake_summary.to_dict()
        else:
            run_timed_flow_stage(
                state,
                "load_duckdb_raw_tables",
                load_duckdb_raw_tables,
                context,
                extraction_paths,
                state.validation_output,
            )

        run_timed_flow_stage(
            state,
            "run_dbt_build",
            run_dbt_build,
            context,
        )

        state.dbt_artifacts = collect_dbt_artifacts(context)
        state.complete("collect_dbt_artifacts")

        if context.is_cloud_route:
            dbt_s3_summary = upload_dbt_artifacts_to_s3(
                context,
                extraction_paths,
                state.dbt_artifacts,
            )
            state.s3_upload_summary["dbt_artifacts"] = dbt_s3_summary.to_dict()
            state.complete("upload_dbt_artifacts_to_s3")

        state.bi_row_counts = run_timed_flow_stage(
            state,
            "validate_bi_tables",
            validate_bi_tables,
            context,
        )

        if not context.is_cloud_route:
            state.export_paths = run_timed_flow_stage(
                state,
                "export_bi_tables",
                export_bi_tables,
                context,
            )

        summary_path = write_state_run_summary(
            context,
            status="success",
            state=state,
        )
        logger.info(
            "%s lending pipeline completed: %s",
            context.run_mode.title(),
            summary_path,
        )
        return str(summary_path)
    except Exception as exc:
        failed_stage = state.failed_stage(context.stage_order)
        summary_path = write_state_run_summary(
            context,
            status="failed",
            state=state,
            failed_stage=failed_stage,
            error_message=str(exc),
        )
        logger.error(
            "%s lending pipeline failed at %s: %s",
            context.run_mode.title(),
            failed_stage,
            exc,
        )
        logger.error("Failure summary written to %s", summary_path)
        raise


def main() -> None:
    from pipelines.cli.run_lending_pipeline import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
