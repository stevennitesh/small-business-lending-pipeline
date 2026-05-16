from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from pipelines.extract.bls_laus_extract import (
    BLSLAUSExtractionSummary,
    extract_bls_laus,
    parse_monthly_period,
)
from pipelines.extract.census_bds_extract import (
    CensusBDSExtractionSummary,
    extract_census_bds,
)
from pipelines.extract.sba_extract import (
    SBAExtractionSummary,
    extract_sba_foia,
)
from pipelines.load.duckdb_loader import RawLoadSummary, load_raw_extracts
from pipelines.load.s3_loader import (
    S3UploadSummary,
    build_dbt_artifact_upload_item,
    upload_items_to_s3,
    upload_run_artifacts_to_s3,
)
from pipelines.load.snowflake_loader import (
    SnowflakeConfig,
    SnowflakeRawLoadSummary,
    connect_to_snowflake,
    load_raw_extracts_to_snowflake_from_s3,
    load_raw_extracts_to_snowflake,
)
from pipelines.storage.raw_artifacts import (
    LocalRawArtifactStore,
    RawArtifactReader,
    S3RawArtifactStore,
)
from pipelines.utils.config import ProjectConfig, SourceIdentity, load_project_config
from pipelines.utils.dates import utc_now_iso
from pipelines.utils.hashing import calculate_sha256, hash_schema
from pipelines.utils.manifest import ExtractionManifest, write_manifest
from pipelines.utils.paths import build_raw_s3_key, build_s3_uri
from pipelines.validation.raw_checks import (
    check_cloud_manifest_storage,
    check_manifest_raw_uri_required,
    check_manifest_source_identity,
    check_raw_manifest,
    check_required_manifest_resource,
    check_validation_output_created,
)
from pipelines.validation.schema_checks import (
    check_bls_laus_payload,
    check_census_bds_payload,
    check_sba_required_resources,
)
from pipelines.validation.validation_result import (
    ValidationFailedError,
    ValidationResult,
    assert_no_blocking_failures,
    write_validation_results,
)


RUN_MODE_ALIASES = {
    "local": "local",
    "cloud": "cloud",
    "final": "cloud",
}

LOCAL_FLOW_STAGES = (
    "initialize_run",
    "load_config",
    "extract_sources",
    "write_manifests",
    "validate_raw_outputs",
    "load_duckdb_raw_tables",
    "run_dbt_build",
    "collect_dbt_artifacts",
    "validate_bi_tables",
    "export_bi_tables",
    "write_run_summary",
)

CLOUD_FLOW_STAGES = (
    "initialize_run",
    "load_config",
    "require_cloud_mode_config",
    "extract_sources",
    "write_manifests",
    "validate_raw_outputs",
    "upload_raw_artifacts_to_s3",
    "load_snowflake_raw_tables",
    "run_dbt_build",
    "collect_dbt_artifacts",
    "upload_dbt_artifacts_to_s3",
    "validate_bi_tables",
    "write_run_summary",
)

# Compatibility alias for older final-mode callers; active route code should use
# CLOUD_FLOW_STAGES.
FINAL_FLOW_STAGES = CLOUD_FLOW_STAGES
FLOW_STAGES = LOCAL_FLOW_STAGES

BI_TABLES = (
    "bi_executive_overview",
    "bi_state_lending_trends",
    "bi_lender_concentration",
    "bi_industry_mix",
    "bi_program_mix",
    "bi_regional_business_health",
    "bi_pipeline_health",
    "bi_lender_mix",
    "bi_state_filter",
)


@dataclass(frozen=True)
class LocalRunContext:
    pipeline_run_id: str
    run_mode: str
    extract_mode: str
    data_root: Path
    duckdb_path: Path
    dbt_project_dir: Path
    dbt_profiles_dir: Path
    dbt_target: str
    run_started_at_utc: str
    s3_bucket: str | None = None
    source_start_year: int | None = None
    source_end_year: int | None = None

    @property
    def is_cloud_route(self) -> bool:
        return self.run_mode == "cloud"

    @property
    def run_validation_dir(self) -> Path:
        return self.data_root / "validation" / f"pipeline_run_id={self.pipeline_run_id}"

    @property
    def run_export_dir(self) -> Path:
        return self.data_root / "exports" / "powerbi" / f"pipeline_run_id={self.pipeline_run_id}"

    @property
    def stage_order(self) -> tuple[str, ...]:
        return CLOUD_FLOW_STAGES if self.is_cloud_route else LOCAL_FLOW_STAGES


@dataclass(frozen=True)
class ExtractionPaths:
    sba_7a_manifest_paths: tuple[Path, ...]
    sba_504_manifest_paths: tuple[Path, ...]
    census_bds_manifest_paths: tuple[Path, ...]
    bls_laus_manifest_paths: tuple[Path, ...]
    manifest_paths: tuple[Path, ...]


@dataclass(frozen=True)
class RawValidationExpectations:
    sba_required_resource_names: list[str]
    census_expected_state_count: int
    bls_expected_series_ids: tuple[str, ...]
    bls_required_period_pattern: str
    bls_unemployment_rate_min: float
    bls_unemployment_rate_max: float


@dataclass(frozen=True)
class DbtBuildResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class PipelineRunSummary:
    pipeline_run_id: str
    run_mode: str
    route: str
    extract_mode: str
    dbt_target: str
    status: str
    completed_stages: list[str]
    failed_stage: str | None
    error_message: str | None
    started_at_utc: str
    finished_at_utc: str
    validation_result_path: str | None = None
    duckdb_path: str | None = None
    dbt_artifacts: dict[str, str] = field(default_factory=dict)
    bi_row_counts: dict[str, int] = field(default_factory=dict)
    export_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    s3_bucket: str | None = None,
    pipeline_run_id: str | None = None,
    source_start_year: int | None = None,
    source_end_year: int | None = None,
) -> LocalRunContext:
    run_mode = _normalize_run_mode(run_mode)
    if extract_mode not in {"fixture", "live"}:
        raise ValueError("extract_mode must be 'fixture' or 'live'.")
    if source_start_year and source_end_year and source_start_year > source_end_year:
        raise ValueError("source_start_year cannot be greater than source_end_year.")

    run_id = pipeline_run_id or f"{run_mode}-{uuid.uuid4()}"
    context = LocalRunContext(
        pipeline_run_id=run_id,
        run_mode=run_mode,
        extract_mode=extract_mode,
        data_root=Path(data_root),
        duckdb_path=Path(duckdb_path),
        dbt_project_dir=Path(dbt_project_dir),
        dbt_profiles_dir=Path(dbt_profiles_dir),
        dbt_target=dbt_target,
        run_started_at_utc=utc_now_iso(),
        s3_bucket=s3_bucket,
        source_start_year=source_start_year,
        source_end_year=source_end_year,
    )
    context.data_root.mkdir(parents=True, exist_ok=True)
    context.run_validation_dir.mkdir(parents=True, exist_ok=True)
    context.run_export_dir.mkdir(parents=True, exist_ok=True)
    return context


@task
def load_config(config_dir: str = "config") -> ProjectConfig:
    return load_project_config(Path(config_dir))


@task
def require_cloud_mode_config(context: LocalRunContext) -> str:
    if not context.is_cloud_route:
        return context.s3_bucket or ""

    load_dotenv(override=True)
    bucket = _s3_bucket(context)
    missing = []
    if not bucket:
        missing.append("S3_BUCKET")
    try:
        SnowflakeConfig.from_env()
    except Exception as exc:
        raise RuntimeError(f"Missing cloud mode configuration: {exc}") from exc
    if missing:
        raise RuntimeError(
            "Missing cloud mode configuration: " + ", ".join(sorted(missing))
        )
    return bucket


require_final_mode_config = require_cloud_mode_config


@task
def extract_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
) -> ExtractionPaths:
    if context.run_mode not in {"local", "cloud"}:
        raise ValueError("run_mode must be 'local' or 'cloud'.")
    if context.extract_mode == "live":
        return _extract_live_sources(context, project_config)
    return _write_local_fixture_extracts(context, project_config)


@task
def validate_raw_outputs(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    project_config: ProjectConfig,
) -> Path:
    validation_results: list[ValidationResult] = []
    manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in extraction_paths.manifest_paths
    ]
    artifact_reader = _raw_artifact_reader(context)

    for manifest_path in extraction_paths.manifest_paths:
        validation_results.extend(
            check_raw_manifest(manifest_path, artifact_reader=artifact_reader)
        )

    for manifest in manifests:
        validation_results.append(
            check_manifest_source_identity(
                manifest,
                expected_identity=project_config.source_identity(
                    _source_name_for_resource(str(manifest["resource_name"]))
                ),
            )
        )
        if context.is_cloud_route:
            validation_results.append(check_manifest_raw_uri_required(manifest))
            validation_results.append(check_cloud_manifest_storage(manifest))

    expectations = _raw_validation_expectations(context, project_config)

    manifests_by_name = manifests_by_resource(manifests)

    if project_config.is_source_enabled("sba_foia"):
        validation_results.extend(
            check_sba_required_resources(
                manifests,
                required_resource_names=expectations.sba_required_resource_names,
                source_identity=project_config.source_identity("sba_foia"),
            )
        )

    if project_config.is_source_enabled("census_bds"):
        census_manifest_result = check_required_manifest_resource(
            manifests,
            resource_name="bds_state_year",
            pipeline_run_id=context.pipeline_run_id,
            source_identity=project_config.source_identity("census_bds"),
        )
        validation_results.append(census_manifest_result)
        if census_manifest_result.status == "passed":
            validation_results.extend(
                check_census_bds_payload(
                    json.loads(
                        artifact_reader.read_text(manifests_by_name["bds_state_year"])
                    ),
                    required_variables=tuple(
                        project_config.validation_thresholds["census_bds"][
                            "required_columns"
                        ]
                    ),
                    expected_state_count=expectations.census_expected_state_count,
                    pipeline_run_id=context.pipeline_run_id,
                    source_identity=project_config.source_identity("census_bds"),
                )
            )

    if project_config.is_source_enabled("bls_laus"):
        bls_manifest_result = check_required_manifest_resource(
            manifests,
            resource_name="laus_state_month",
            pipeline_run_id=context.pipeline_run_id,
            source_identity=project_config.source_identity("bls_laus"),
        )
        validation_results.append(bls_manifest_result)
        if bls_manifest_result.status == "passed":
            validation_results.extend(
                check_bls_laus_payload(
                    json.loads(
                        artifact_reader.read_text(manifests_by_name["laus_state_month"])
                    ),
                    expected_series_ids=expectations.bls_expected_series_ids,
                    pipeline_run_id=context.pipeline_run_id,
                    required_period_pattern=expectations.bls_required_period_pattern,
                    unemployment_rate_min=expectations.bls_unemployment_rate_min,
                    unemployment_rate_max=expectations.bls_unemployment_rate_max,
                    source_identity=project_config.source_identity("bls_laus"),
                )
            )

    validation_path = context.run_validation_dir / "validation_results.json"
    write_validation_results(validation_results, validation_path)
    validation_results.append(
        check_validation_output_created(
            validation_path,
            pipeline_run_id=context.pipeline_run_id,
            source_system="pipeline",
            source_dataset="raw_validation",
            source_resource_name="validation_results",
        )
    )
    write_validation_results(validation_results, validation_path)
    assert_no_blocking_failures(validation_results)
    return validation_path


@task
def load_duckdb_raw_tables(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_result_path: Path,
) -> RawLoadSummary:
    return load_raw_extracts(
        duckdb_path=context.duckdb_path,
        sba_7a_manifest_paths=extraction_paths.sba_7a_manifest_paths,
        sba_504_manifest_paths=extraction_paths.sba_504_manifest_paths,
        census_bds_manifest_paths=extraction_paths.census_bds_manifest_paths,
        bls_laus_manifest_paths=extraction_paths.bls_laus_manifest_paths,
        validation_result_paths=[validation_result_path],
    )


@task
def upload_raw_artifacts_to_s3(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_result_path: Path,
) -> S3UploadSummary:
    return upload_run_artifacts_to_s3(
        manifest_paths=list(extraction_paths.manifest_paths),
        validation_result_path=validation_result_path,
        bucket=_s3_bucket(context),
        run_mode=context.run_mode,
    )


@task
def load_snowflake_raw_tables(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_result_path: Path,
) -> SnowflakeRawLoadSummary:
    config = SnowflakeConfig.from_env()
    connection = connect_to_snowflake(config)
    try:
        return load_raw_extracts_to_snowflake_from_s3(
            connection=connection,
            database=config.database,
            raw_schema=config.raw_schema,
            audit_schema=config.audit_schema,
            sba_7a_manifest_paths=extraction_paths.sba_7a_manifest_paths,
            sba_504_manifest_paths=extraction_paths.sba_504_manifest_paths,
            census_bds_manifest_paths=extraction_paths.census_bds_manifest_paths,
            bls_laus_manifest_paths=extraction_paths.bls_laus_manifest_paths,
            validation_result_paths=[validation_result_path],
            storage_integration=config.storage_integration,
        )
    finally:
        connection.close()


@task
def run_dbt_build(context: LocalRunContext) -> DbtBuildResult:
    load_dotenv(override=True)
    _ensure_dbt_profile(context)
    dbt_executable = _dbt_executable()
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


@task
def collect_dbt_artifacts(context: LocalRunContext) -> dict[str, str]:
    target_dir = context.dbt_project_dir / "target"
    artifacts = {
        name: str(target_dir / name)
        for name in ("manifest.json", "run_results.json")
        if (target_dir / name).is_file()
    }
    if not artifacts:
        raise RuntimeError("dbt build did not produce target artifacts.")
    return artifacts


@task
def upload_dbt_artifacts_to_s3(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    dbt_artifacts: dict[str, str],
) -> S3UploadSummary:
    if not dbt_artifacts:
        return S3UploadSummary(bucket=_s3_bucket(context), uploaded_objects=())

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
        bucket=_s3_bucket(context),
        required=context.is_cloud_route,
    )


@task
def validate_bi_tables(context: LocalRunContext) -> dict[str, int]:
    if context.is_cloud_route:
        return _validate_snowflake_bi_tables()

    row_counts: dict[str, int] = {}
    with duckdb.connect(str(context.duckdb_path)) as connection:
        for table_name in BI_TABLES:
            row_count = int(
                connection.execute(f"select count(*) from {table_name}").fetchone()[0]
            )
            if row_count <= 0:
                raise RuntimeError(f"BI table {table_name} has no rows.")
            row_counts[table_name] = row_count
    return row_counts


@task
def export_bi_tables(context: LocalRunContext) -> list[str]:
    context.run_export_dir.mkdir(parents=True, exist_ok=True)
    export_paths: list[str] = []
    with duckdb.connect(str(context.duckdb_path)) as connection:
        for table_name in BI_TABLES:
            export_path = context.run_export_dir / f"{table_name}.csv"
            connection.execute(
                f"copy (select * from {table_name}) to ? (header, delimiter ',')",
                [str(export_path)],
            )
            export_paths.append(str(export_path))
    return export_paths


@task
def write_run_summary(
    context: LocalRunContext,
    *,
    status: str,
    completed_stages: list[str],
    failed_stage: str | None = None,
    error_message: str | None = None,
    validation_result_path: Path | None = None,
    dbt_artifacts: dict[str, str] | None = None,
    bi_row_counts: dict[str, int] | None = None,
    export_paths: list[str] | None = None,
    s3_upload_summary: dict[str, Any] | None = None,
    snowflake_raw_load_summary: dict[str, Any] | None = None,
) -> Path:
    summary = PipelineRunSummary(
        pipeline_run_id=context.pipeline_run_id,
        run_mode=context.run_mode,
        route=context.run_mode,
        extract_mode=context.extract_mode,
        dbt_target=context.dbt_target,
        status=status,
        completed_stages=completed_stages,
        failed_stage=failed_stage,
        error_message=error_message,
        started_at_utc=context.run_started_at_utc,
        finished_at_utc=utc_now_iso(),
        validation_result_path=str(validation_result_path) if validation_result_path else None,
        duckdb_path=str(context.duckdb_path),
        dbt_artifacts=dbt_artifacts or {},
        bi_row_counts=bi_row_counts or {},
        export_paths=export_paths or [],
    )
    summary_path = context.run_validation_dir / "run_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                **summary.to_dict(),
                "s3_upload_summary": s3_upload_summary or {},
                "snowflake_raw_load_summary": snowflake_raw_load_summary or {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary_path


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
    s3_bucket: str | None = None,
    pipeline_run_id: str | None = None,
    source_start_year: int | None = None,
    source_end_year: int | None = None,
) -> str:
    logger = get_run_logger()
    completed_stages: list[str] = []
    context = initialize_run(
        run_mode=run_mode,
        extract_mode=extract_mode,
        dbt_target=dbt_target,
        data_root=data_root,
        duckdb_path=duckdb_path,
        dbt_project_dir=dbt_project_dir,
        dbt_profiles_dir=dbt_profiles_dir,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        source_start_year=source_start_year,
        source_end_year=source_end_year,
    )
    completed_stages.append("initialize_run")

    validation_result_path: Path | None = None
    dbt_artifacts: dict[str, str] = {}
    bi_row_counts: dict[str, int] = {}
    export_paths: list[str] = []
    s3_upload_summary: dict[str, Any] = {}
    snowflake_raw_load_summary: dict[str, Any] = {}
    failed_stage: str | None = None

    try:
        project_config = load_config()
        completed_stages.append("load_config")

        if context.is_cloud_route:
            require_cloud_mode_config(context)
            completed_stages.append("require_cloud_mode_config")

        extraction_paths = extract_sources(context, project_config)
        completed_stages.extend(["extract_sources", "write_manifests"])

        validation_result_path = validate_raw_outputs(
            context,
            extraction_paths,
            project_config,
        )
        completed_stages.append("validate_raw_outputs")

        if context.is_cloud_route:
            raw_s3_summary = upload_raw_artifacts_to_s3(
                context,
                extraction_paths,
                validation_result_path,
            )
            s3_upload_summary["raw_artifacts"] = raw_s3_summary.to_dict()
            completed_stages.append("upload_raw_artifacts_to_s3")

            snowflake_summary = load_snowflake_raw_tables(
                context,
                extraction_paths,
                validation_result_path,
            )
            snowflake_raw_load_summary = snowflake_summary.to_dict()
            completed_stages.append("load_snowflake_raw_tables")
        else:
            load_duckdb_raw_tables(context, extraction_paths, validation_result_path)
            completed_stages.append("load_duckdb_raw_tables")

        run_dbt_build(context)
        completed_stages.append("run_dbt_build")

        dbt_artifacts = collect_dbt_artifacts(context)
        completed_stages.append("collect_dbt_artifacts")

        if context.is_cloud_route:
            dbt_s3_summary = upload_dbt_artifacts_to_s3(
                context,
                extraction_paths,
                dbt_artifacts,
            )
            s3_upload_summary["dbt_artifacts"] = dbt_s3_summary.to_dict()
            completed_stages.append("upload_dbt_artifacts_to_s3")

        bi_row_counts = validate_bi_tables(context)
        completed_stages.append("validate_bi_tables")

        if context.run_mode == "local":
            export_paths = export_bi_tables(context)
            completed_stages.append("export_bi_tables")

        summary_path = write_run_summary(
            context,
            status="success",
            completed_stages=completed_stages + ["write_run_summary"],
            validation_result_path=validation_result_path,
            dbt_artifacts=dbt_artifacts,
            bi_row_counts=bi_row_counts,
            export_paths=export_paths,
            s3_upload_summary=s3_upload_summary,
            snowflake_raw_load_summary=snowflake_raw_load_summary,
        )
        logger.info(
            "%s lending pipeline completed: %s",
            context.run_mode.title(),
            summary_path,
        )
        return str(summary_path)
    except Exception as exc:
        failed_stage = _failed_stage(completed_stages, context.stage_order)
        summary_path = write_run_summary(
            context,
            status="failed",
            completed_stages=completed_stages + ["write_run_summary"],
            failed_stage=failed_stage,
            error_message=str(exc),
            validation_result_path=validation_result_path,
            dbt_artifacts=dbt_artifacts,
            bi_row_counts=bi_row_counts,
            export_paths=export_paths,
            s3_upload_summary=s3_upload_summary,
            snowflake_raw_load_summary=snowflake_raw_load_summary,
        )
        logger.error(
            "%s lending pipeline failed at %s: %s",
            context.run_mode.title(),
            failed_stage,
            exc,
        )
        logger.error("Failure summary written to %s", summary_path)
        raise


def manifests_by_resource(manifests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(manifest["resource_name"]): manifest for manifest in manifests}


def _normalize_run_mode(run_mode: str) -> str:
    try:
        return RUN_MODE_ALIASES[run_mode]
    except KeyError as exc:
        allowed = ", ".join(sorted(RUN_MODE_ALIASES))
        raise ValueError(f"run_mode must be one of: {allowed}") from exc


def _extract_live_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
) -> ExtractionPaths:
    load_dotenv(override=True)
    bucket = _s3_bucket(context) or "local-live"
    raw_artifact_store = _raw_artifact_store(context, bucket)
    sba_manifest_paths: dict[str, Path] = {}
    census_bds_manifest_paths: tuple[Path, ...] = ()
    bls_laus_manifest_paths: tuple[Path, ...] = ()

    if project_config.is_source_enabled("sba_foia"):
        sba_summary = extract_sba_foia(
            config=project_config.sba,
            source_identity=project_config.source_identity("sba_foia"),
            data_root=context.data_root,
            s3_bucket=bucket,
            pipeline_run_id=context.pipeline_run_id,
            raw_artifact_store=raw_artifact_store,
        )
        sba_manifest_paths = sba_summary.manifest_paths

    if project_config.is_source_enabled("census_bds"):
        census_summary = extract_census_bds(
            config=project_config.census_bds,
            source_identity=project_config.source_identity("census_bds"),
            data_root=context.data_root,
            s3_bucket=bucket,
            pipeline_run_id=context.pipeline_run_id,
            start_year=context.source_start_year,
            end_year=context.source_end_year,
            raw_artifact_store=raw_artifact_store,
        )
        census_bds_manifest_paths = (census_summary.manifest_path,)

    if project_config.is_source_enabled("bls_laus"):
        requested_bls_start_year = (
            context.source_start_year or project_config.bls_laus.start_year
        )
        bls_start_year = max(requested_bls_start_year - 1, 1976)
        bls_summary = extract_bls_laus(
            config=project_config.bls_laus,
            source_identity=project_config.source_identity("bls_laus"),
            data_root=context.data_root,
            s3_bucket=bucket,
            pipeline_run_id=context.pipeline_run_id,
            start_year=bls_start_year,
            end_year=context.source_end_year,
            raw_artifact_store=raw_artifact_store,
        )
        bls_laus_manifest_paths = (bls_summary.manifest_path,)

    sba_7a_manifest_paths = _sba_manifest_paths_by_program(
        sba_manifest_paths,
        "sba_7a_",
    )
    sba_504_manifest_paths = _sba_manifest_paths_by_program(
        sba_manifest_paths,
        "sba_504_",
    )
    if project_config.is_source_enabled("sba_foia") and (
        not sba_7a_manifest_paths or not sba_504_manifest_paths
    ):
        raise RuntimeError(
            "Live SBA extraction did not produce both 7(a) and 504 manifests."
        )

    return ExtractionPaths(
        sba_7a_manifest_paths=sba_7a_manifest_paths,
        sba_504_manifest_paths=sba_504_manifest_paths,
        census_bds_manifest_paths=census_bds_manifest_paths,
        bls_laus_manifest_paths=bls_laus_manifest_paths,
        manifest_paths=tuple(
            [
                *sba_manifest_paths.values(),
                *census_bds_manifest_paths,
                *bls_laus_manifest_paths,
            ]
        ),
    )


def _sba_manifest_paths_by_program(
    manifest_paths: dict[str, Path],
    logical_name_prefix: str,
) -> tuple[Path, ...]:
    return tuple(
        manifest_path
        for logical_name, manifest_path in sorted(manifest_paths.items())
        if logical_name.startswith(logical_name_prefix)
    )


def _raw_artifact_store(
    context: LocalRunContext,
    bucket: str,
    s3_client=None,
) -> LocalRawArtifactStore | S3RawArtifactStore:
    if context.is_cloud_route:
        return S3RawArtifactStore(bucket=bucket, s3_client=s3_client)
    return LocalRawArtifactStore(data_root=context.data_root, s3_bucket=bucket)


def _raw_artifact_reader(
    context: LocalRunContext,
    s3_client=None,
) -> RawArtifactReader:
    return RawArtifactReader(s3_client=s3_client if context.is_cloud_route else None)


def _raw_validation_expectations(
    context: LocalRunContext,
    project_config: ProjectConfig,
) -> RawValidationExpectations:
    if context.extract_mode == "fixture":
        return RawValidationExpectations(
            sba_required_resource_names=[
                "sba_7a_fy2020_present",
                "sba_504_fy2010_present",
            ],
            census_expected_state_count=2,
            bls_expected_series_ids=(
                "LASST010000000000003",
                "LASST170000000000003",
            ),
            bls_required_period_pattern=r"^M(0[1-9]|1[0-2])$",
            bls_unemployment_rate_min=0,
            bls_unemployment_rate_max=100,
        )

    required_sba_programs = (
        {
            str(program)
            for program in project_config.validation_thresholds["sba_foia"].get(
                "required_programs",
                (),
            )
        }
        if project_config.is_source_enabled("sba_foia")
        else set()
    )
    required_sba_resources = [
        spec.logical_name
        for spec in project_config.sba.resources
        if project_config.is_source_enabled("sba_foia")
        and spec.required
        and spec.program in required_sba_programs
    ]
    bls_thresholds = project_config.validation_thresholds.get("bls_laus", {})
    return RawValidationExpectations(
        sba_required_resource_names=required_sba_resources,
        census_expected_state_count=(
            int(project_config.validation_thresholds["census_bds"]["min_rows"])
            if project_config.is_source_enabled("census_bds")
            else 0
        ),
        bls_expected_series_ids=tuple(
            series.series_id for series in project_config.bls_laus.series
        )
        if project_config.is_source_enabled("bls_laus")
        else (),
        bls_required_period_pattern=str(
            bls_thresholds.get("required_period_pattern", r"^M(0[1-9]|1[0-2])$")
        ),
        bls_unemployment_rate_min=float(
            bls_thresholds.get("unemployment_rate_min", 0)
        ),
        bls_unemployment_rate_max=float(
            bls_thresholds.get("unemployment_rate_max", 100)
        ),
    )


def _write_local_fixture_extracts(
    context: LocalRunContext,
    project_config: ProjectConfig,
) -> ExtractionPaths:
    raw_paths = _write_fixture_raw_files(context)
    manifest_paths = {
        resource_name: _write_fixture_manifest(
            context=context,
            resource_name=resource_name,
            raw_file_path=raw_file_path,
            row_count=row_count,
            file_format=file_format,
            schema_fields=schema_fields,
            source_identity=project_config.source_identity(
                _source_name_for_resource(resource_name)
            ),
        )
        for resource_name, (
            raw_file_path,
            row_count,
            file_format,
            schema_fields,
        ) in raw_paths.items()
    }
    return ExtractionPaths(
        sba_7a_manifest_paths=(manifest_paths["sba_7a_fy2020_present"],),
        sba_504_manifest_paths=(manifest_paths["sba_504_fy2010_present"],),
        census_bds_manifest_paths=(manifest_paths["bds_state_year"],),
        bls_laus_manifest_paths=(manifest_paths["laus_state_month"],),
        manifest_paths=tuple(manifest_paths.values()),
    )


def _write_fixture_raw_files(
    context: LocalRunContext,
) -> dict[str, tuple[Path, int, str, list[str]]]:
    output: dict[str, tuple[Path, int, str, list[str]]] = {}

    sba_7a_rows = [_sba_7a_row()]
    sba_7a_path = _raw_path(
        context,
        "sba",
        "7a_foia",
        "source_period=fy2020_present",
        "sba_7a_fixture.csv",
    )
    _write_csv(sba_7a_path, sba_7a_rows)
    output["sba_7a_fy2020_present"] = (
        sba_7a_path,
        len(sba_7a_rows),
        "csv",
        list(sba_7a_rows[0]),
    )

    sba_504_rows = [_sba_504_row()]
    sba_504_path = _raw_path(
        context,
        "sba",
        "504_foia",
        "source_period=fy2010_present",
        "sba_504_fixture.csv",
    )
    _write_csv(sba_504_path, sba_504_rows)
    output["sba_504_fy2010_present"] = (
        sba_504_path,
        len(sba_504_rows),
        "csv",
        list(sba_504_rows[0]),
    )

    census_payload = [
        [
            "NAME",
            "YEAR",
            "ESTAB",
            "ESTABS_ENTRY",
            "ESTABS_ENTRY_RATE",
            "ESTABS_EXIT",
            "ESTABS_EXIT_RATE",
            "FIRM",
            "JOB_CREATION",
            "JOB_DESTRUCTION",
            "time",
            "state",
        ],
        [
            "Alabama",
            "2026",
            "10",
            "2",
            "20.0",
            "1",
            "10.0",
            "8",
            "30",
            "15",
            "2026",
            "01",
        ],
        [
            "Illinois",
            "2026",
            "20",
            "3",
            "15.0",
            "2",
            "10.0",
            "15",
            "40",
            "20",
            "2026",
            "17",
        ],
    ]
    census_path = _raw_path(
        context,
        "census",
        "bds",
        "grain=state_year",
        "bds_state_year_fixture.json",
    )
    census_path.write_text(json.dumps(census_payload, indent=2) + "\n", encoding="utf-8")
    output["bds_state_year"] = (
        census_path,
        len(census_payload) - 1,
        "json",
        census_payload[0],
    )

    bls_payload = {
        "normalized_rows": [
            _bls_row(
                "LASST010000000000003",
                "01",
                "AL",
                "Alabama",
                "2026",
                "M01",
                3.1,
            ),
            _bls_row(
                "LASST170000000000003",
                "17",
                "IL",
                "Illinois",
                "2026",
                "M01",
                4.2,
            ),
        ]
    }
    bls_path = _raw_path(
        context,
        "bls",
        "laus",
        "grain=state_month",
        "bls_laus_state_month_fixture.json",
    )
    bls_path.write_text(json.dumps(bls_payload, indent=2) + "\n", encoding="utf-8")
    output["laus_state_month"] = (
        bls_path,
        len(bls_payload["normalized_rows"]),
        "json",
        list(bls_payload["normalized_rows"][0]),
    )
    return output


def _write_fixture_manifest(
    *,
    context: LocalRunContext,
    resource_name: str,
    raw_file_path: Path,
    row_count: int,
    file_format: str,
    schema_fields: list[str],
    source_identity: SourceIdentity,
) -> Path:
    source_system = source_identity.source_system
    dataset_name = source_identity.dataset_name
    ingestion_date = date.fromisoformat(context.run_started_at_utc[:10]).isoformat()
    s3_raw_key = build_raw_s3_key(
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        ingestion_date=ingestion_date,
        pipeline_run_id=context.pipeline_run_id,
        filename=raw_file_path.name,
    )
    manifest = ExtractionManifest(
        pipeline_run_id=context.pipeline_run_id,
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        source_url=f"fixture://{resource_name}",
        extracted_at_utc=context.run_started_at_utc,
        ingestion_date=ingestion_date,
        local_raw_path=str(raw_file_path),
        s3_raw_uri=build_s3_uri(context.s3_bucket or "local-fixtures", s3_raw_key),
        file_format=file_format,
        row_count=row_count,
        sha256_checksum=calculate_sha256(raw_file_path),
        schema_hash=hash_schema(schema_fields),
        validation_status="passed",
        request_parameters={"run_mode": context.run_mode},
        column_count=len(schema_fields),
        file_size_bytes=raw_file_path.stat().st_size,
        validation_messages=[],
    )
    manifest_path = (
        context.data_root
        / "manifests"
        / source_system
        / f"pipeline_run_id={context.pipeline_run_id}"
        / f"{resource_name}.manifest.json"
    )
    write_manifest(manifest, manifest_path)
    return manifest_path


def _raw_path(
    context: LocalRunContext,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    filename: str,
) -> Path:
    path = (
        context.data_root
        / "raw"
        / source_system
        / dataset_name
        / resource_name
        / f"pipeline_run_id={context.pipeline_run_id}"
        / filename
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _sba_7a_row() -> dict[str, Any]:
    return {
        "asofdate": "3/31/2026",
        "program": "7A",
        "locationid": "1",
        "borrname": "Fixture 7A LLC",
        "borrstreet": "1 Main St",
        "borrcity": "Birmingham",
        "borrstate": "AL",
        "borrzip": "35203",
        "bankname": "Fixture Bank, Inc.",
        "bankfdicnumber": "123",
        "bankncuanumber": "",
        "bankstreet": "2 Bank St",
        "bankcity": "Birmingham",
        "bankstate": "AL",
        "bankzip": "35203",
        "grossapproval": "1000",
        "sbaguaranteedapproval": "750",
        "approvaldate": "1/15/2026",
        "approvalfy": "2026",
        "firstdisbursementdate": "2/1/2026",
        "processingmethod": "Preferred Lenders Program",
        "subprogram": "Guaranty",
        "initialinterestrate": "6",
        "fixedorvariableinterestind": "V",
        "terminmonths": "120",
        "naicscode": "541611",
        "naicsdescription": "Administrative Management",
        "franchisecode": "",
        "franchisename": "",
        "projectcounty": "JEFFERSON",
        "projectstate": "AL",
        "sbadistrictoffice": "ALABAMA DISTRICT OFFICE",
        "congressionaldistrict": "7",
        "businesstype": "CORPORATION",
        "businessage": "Existing",
        "loanstatus": "PIF",
        "paidinfulldate": "",
        "chargeoffdate": "",
        "grosschargeoffamount": "0",
        "revolverstatus": "FALSE",
        "jobssupported": "4",
        "collateralind": "TRUE",
        "soldsecmrktind": "Y",
    }


def _sba_504_row() -> dict[str, Any]:
    return {
        "asofdate": "3/31/2026",
        "program": "504",
        "locationid": "2",
        "borrname": "Fixture 504 Inc.",
        "borrstreet": "10 Market St",
        "borrcity": "Chicago",
        "borrstate": "IL",
        "borrzip": "60601",
        "cdc_name": "Fixture CDC",
        "cdc_street": "20 CDC St",
        "cdc_city": "Chicago",
        "cdc_state": "IL",
        "cdc_zip": "60601",
        "thirdpartylender_name": "Third Party Bank",
        "thirdpartylender_city": "Chicago",
        "thirdpartylender_state": "IL",
        "thirdpartydollars": "2500",
        "grossapproval": "3000",
        "approvaldate": "2/20/2026",
        "approvalfy": "2026",
        "firstdisbursementdate": "3/1/2026",
        "processingmethod": "504 Basic",
        "subprogram": "Sec. 504",
        "terminmonths": "240",
        "naicscode": "721110",
        "naicsdescription": "Hotels",
        "franchisecode": "",
        "franchisename": "",
        "projectcounty": "COOK",
        "projectstate": "IL",
        "sbadistrictoffice": "ILLINOIS DISTRICT OFFICE",
        "congressionaldistrict": "1",
        "businesstype": "CORPORATION",
        "businessage": "Existing",
        "loanstatus": "PIF",
        "paidinfulldate": "",
        "chargeoffdate": "",
        "grosschargeoffamount": "0",
        "jobssupported": "8",
        "collateralind": "TRUE",
    }


def _bls_row(
    series_id: str,
    state_fips: str,
    state_abbr: str,
    state_name: str,
    year: str,
    period: str,
    value: float,
) -> dict[str, Any]:
    observed_month = parse_monthly_period(year, period)
    if observed_month is None:
        raise ValueError(f"Invalid fixture BLS monthly period: {period}")
    return {
        "series_id": series_id,
        "state_fips": state_fips,
        "state_abbr": state_abbr,
        "state_name": state_name,
        "year": int(year),
        "period": period,
        "observed_month": observed_month.isoformat(),
        "value": value,
        "footnotes": [],
    }


def _source_name_for_resource(resource_name: str) -> str:
    if resource_name.startswith("sba_"):
        return "sba_foia"
    if resource_name == "bds_state_year":
        return "census_bds"
    if resource_name == "laus_state_month":
        return "bls_laus"
    raise ValueError(f"Unsupported fixture resource: {resource_name}")


def _ensure_dbt_profile(context: LocalRunContext) -> None:
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
      threads: 4
""",
        encoding="utf-8",
    )


def _dbt_executable() -> Path:
    executable = Path(sys.executable).with_name("dbt")
    if executable.is_file():
        return executable
    return Path("dbt")


def _validate_snowflake_bi_tables() -> dict[str, int]:
    config = SnowflakeConfig.from_env()
    connection = connect_to_snowflake(config)
    try:
        row_counts: dict[str, int] = {}
        with connection.cursor() as cursor:
            for table_name in BI_TABLES:
                cursor.execute(f"select count(*) from BI.{table_name.upper()}")
                row_count = int(cursor.fetchone()[0])
                if row_count <= 0:
                    raise RuntimeError(f"BI table BI.{table_name.upper()} has no rows.")
                row_counts[table_name] = row_count
        return row_counts
    finally:
        connection.close()


def _s3_bucket(context: LocalRunContext) -> str | None:
    return context.s3_bucket or os.getenv("S3_BUCKET") or None


def _failed_stage(
    completed_stages: list[str],
    stage_order: tuple[str, ...] = FLOW_STAGES,
) -> str:
    for stage in stage_order:
        if stage not in completed_stages and stage != "write_run_summary":
            return stage
    return "unknown"


def main() -> None:
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
    parser.add_argument("--s3-bucket")
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--source-start-year", type=int)
    parser.add_argument("--source-end-year", type=int)
    args = parser.parse_args()

    summary_path = lending_pipeline_flow(
        run_mode=args.run_mode,
        extract_mode=args.extract_mode,
        dbt_target=args.dbt_target,
        data_root=args.data_root,
        duckdb_path=args.duckdb_path,
        dbt_project_dir=args.dbt_project_dir,
        dbt_profiles_dir=args.dbt_profiles_dir,
        s3_bucket=args.s3_bucket,
        pipeline_run_id=args.pipeline_run_id,
        source_start_year=args.source_start_year,
        source_end_year=args.source_end_year,
    )
    print(summary_path)


if __name__ == "__main__":
    main()
