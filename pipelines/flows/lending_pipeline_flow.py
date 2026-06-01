from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task

from pipelines.flows import (
    dbt_bi,
    raw_loads,
    raw_validation,
    run_setup,
    run_summary,
    source_extracts,
)
from pipelines.flows.run_models import (
    CLOUD_FLOW_STAGES,
    LOCAL_FLOW_STAGES,
    DbtBuildResult,
    ExtractionPaths,
    FlowRunState,
    LocalRunContext,
)
from pipelines.flows.raw_loads import RawLoadSummary, S3UploadSummary
from pipelines.flows.raw_loads import SnowflakeRawLoadSummary
from pipelines.utils.config import ProjectConfig, load_project_config
from pipelines.validation.raw_validation_models import RawValidationOutput


BI_TABLES = dbt_bi.BI_TABLES


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
    return load_project_config(Path(config_dir))


@task
def require_cloud_mode_config(context: LocalRunContext) -> str:
    return run_setup.require_cloud_mode_config_for_context(context)


@task
def extract_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
) -> ExtractionPaths:
    if context.run_mode not in {"local", "cloud"}:
        raise ValueError("run_mode must be 'local' or 'cloud'.")
    if context.extract_mode == "live":
        return source_extracts.extract_live_sources(context, project_config)
    return source_extracts.extract_fixture_sources_for_flow(context, project_config)


@task
def validate_raw_outputs(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    project_config: ProjectConfig,
) -> RawValidationOutput:
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
    return raw_loads.load_snowflake_raw_tables_for_context(
        context,
        extraction_paths,
        validation_output,
    )


@task
def run_dbt_build(context: LocalRunContext) -> DbtBuildResult:
    return dbt_bi.run_dbt_build_for_context(context)


@task
def collect_dbt_artifacts(context: LocalRunContext) -> dict[str, str]:
    return dbt_bi.collect_dbt_artifacts_for_context(context)


@task
def upload_dbt_artifacts_to_s3(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    dbt_artifacts: dict[str, str],
) -> S3UploadSummary:
    return dbt_bi.upload_dbt_artifacts_for_context(
        context,
        extraction_paths,
        dbt_artifacts,
    )


@task
def validate_bi_tables(context: LocalRunContext) -> dict[str, int]:
    return dbt_bi.validate_bi_tables_for_context(context)


@task
def export_bi_tables(context: LocalRunContext) -> list[str]:
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

        extraction_paths = _run_timed_stage(
            state.stage_durations_seconds,
            "extract_sources",
            extract_sources,
            context,
            project_config,
        )
        state.manifest_artifact_uris = [
            location.artifact_uri for location in extraction_paths.manifest_locations
        ]
        state.complete_many(["extract_sources", "write_manifests"])

        state.validation_output = _run_timed_stage(
            state.stage_durations_seconds,
            "validate_raw_outputs",
            validate_raw_outputs,
            context,
            extraction_paths,
            project_config,
        )
        state.complete("validate_raw_outputs")

        if context.is_cloud_route:
            raw_s3_summary = _run_timed_stage(
                state.stage_durations_seconds,
                "record_raw_artifact_locations",
                record_raw_artifact_locations,
                context,
                extraction_paths,
                state.validation_output,
            )
            state.s3_upload_summary["raw_artifacts"] = raw_s3_summary.to_dict()
            state.complete("record_raw_artifact_locations")

            snowflake_summary = _run_timed_stage(
                state.stage_durations_seconds,
                "load_snowflake_raw_tables",
                load_snowflake_raw_tables,
                context,
                extraction_paths,
                state.validation_output,
            )
            state.snowflake_raw_load_summary = snowflake_summary.to_dict()
            state.complete("load_snowflake_raw_tables")
        else:
            _run_timed_stage(
                state.stage_durations_seconds,
                "load_duckdb_raw_tables",
                load_duckdb_raw_tables,
                context,
                extraction_paths,
                state.validation_output,
            )
            state.complete("load_duckdb_raw_tables")

        _run_timed_stage(
            state.stage_durations_seconds,
            "run_dbt_build",
            run_dbt_build,
            context,
        )
        state.complete("run_dbt_build")

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

        state.bi_row_counts = _run_timed_stage(
            state.stage_durations_seconds,
            "validate_bi_tables",
            validate_bi_tables,
            context,
        )
        state.complete("validate_bi_tables")

        if context.run_mode == "local":
            state.export_paths = _run_timed_stage(
                state.stage_durations_seconds,
                "export_bi_tables",
                export_bi_tables,
                context,
            )
            state.complete("export_bi_tables")

        summary_path = write_run_summary(
            context,
            status="success",
            completed_stages=state.completed_with_summary(),
            validation_result_path=state.validation_output,
            manifest_artifact_uris=state.manifest_artifact_uris,
            dbt_artifacts=state.dbt_artifacts,
            bi_row_counts=state.bi_row_counts,
            export_paths=state.export_paths,
            s3_upload_summary=state.s3_upload_summary,
            snowflake_raw_load_summary=state.snowflake_raw_load_summary,
            stage_durations_seconds=state.stage_durations_seconds,
        )
        logger.info(
            "%s lending pipeline completed: %s",
            context.run_mode.title(),
            summary_path,
        )
        return str(summary_path)
    except Exception as exc:
        failed_stage = state.failed_stage(context.stage_order)
        summary_path = write_run_summary(
            context,
            status="failed",
            completed_stages=state.completed_with_summary(),
            failed_stage=failed_stage,
            error_message=str(exc),
            validation_result_path=state.validation_output,
            manifest_artifact_uris=state.manifest_artifact_uris,
            dbt_artifacts=state.dbt_artifacts,
            bi_row_counts=state.bi_row_counts,
            export_paths=state.export_paths,
            s3_upload_summary=state.s3_upload_summary,
            snowflake_raw_load_summary=state.snowflake_raw_load_summary,
            stage_durations_seconds=state.stage_durations_seconds,
        )
        logger.error(
            "%s lending pipeline failed at %s: %s",
            context.run_mode.title(),
            failed_stage,
            exc,
        )
        logger.error("Failure summary written to %s", summary_path)
        raise


def _run_timed_stage(
    stage_durations_seconds: dict[str, float],
    stage_name: str,
    stage_callable,
    *args,
    **kwargs,
):
    started_at = time.perf_counter()
    try:
        return stage_callable(*args, **kwargs)
    finally:
        stage_durations_seconds[stage_name] = round(
            time.perf_counter() - started_at,
            3,
        )


def main() -> None:
    from pipelines.cli.run_lending_pipeline import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
