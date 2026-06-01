"""Flow adapters for loading validated raw artifacts into warehouses."""

from __future__ import annotations

from pipelines.flows.run_setup import resolve_s3_bucket
from pipelines.flows.extraction_manifests import ExtractionPaths
from pipelines.flows.run_models import (
    LocalRunContext,
)
from pipelines.load.duckdb_loader import RawLoadSummary, load_raw_extracts
from pipelines.load.s3_loader import S3UploadSummary, upload_run_artifacts_to_s3
from pipelines.load.snowflake_loader import (
    SnowflakeConfig,
    SnowflakeRawLoadSummary,
    connect_to_snowflake,
    load_raw_extracts_to_snowflake_from_s3,
)
from pipelines.validation.raw_validation_models import RawValidationOutput


def load_duckdb_raw_tables_for_context(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_output: RawValidationOutput,
) -> RawLoadSummary:
    """Load local validated raw artifacts into DuckDB raw tables."""
    return load_raw_extracts(
        duckdb_path=context.duckdb_path,
        sba_7a_manifest_paths=extraction_paths.sba_7a_manifest_paths,
        sba_504_manifest_paths=extraction_paths.sba_504_manifest_paths,
        census_bds_manifest_paths=extraction_paths.census_bds_manifest_paths,
        bls_laus_manifest_paths=extraction_paths.bls_laus_manifest_paths,
        validation_result_paths=[validation_output.local_path],
    )


def record_raw_artifact_locations_for_context(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_output: RawValidationOutput,
) -> S3UploadSummary:
    """Return uploaded raw artifact references for cloud/local summary output."""
    if context.is_cloud_route and validation_output.artifact_location is not None:
        uploaded_objects = [
            *(
                location.artifact_uri
                for location in extraction_paths.manifest_locations
            ),
            validation_output.artifact_location.artifact_uri,
        ]
        return S3UploadSummary(
            bucket=resolve_s3_bucket(context),
            uploaded_objects=tuple(uploaded_objects),
        )
    return upload_run_artifacts_to_s3(
        manifest_paths=list(extraction_paths.manifest_paths),
        validation_result_path=validation_output.local_path,
        bucket=resolve_s3_bucket(context),
        run_mode=context.run_mode,
    )


def load_snowflake_raw_tables_for_context(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    validation_output: RawValidationOutput,
) -> SnowflakeRawLoadSummary:
    """Load cloud-route raw artifacts into Snowflake from manifest references."""
    config = SnowflakeConfig.from_env()
    connection = connect_to_snowflake(config)
    try:
        return load_raw_extracts_to_snowflake_from_s3(
            connection=connection,
            database=config.database,
            raw_schema=config.raw_schema,
            audit_schema=config.audit_schema,
            sba_7a_manifest_paths=(
                extraction_paths.sba_7a_manifest_locations
                or extraction_paths.sba_7a_manifest_paths
            ),
            sba_504_manifest_paths=(
                extraction_paths.sba_504_manifest_locations
                or extraction_paths.sba_504_manifest_paths
            ),
            census_bds_manifest_paths=(
                extraction_paths.census_bds_manifest_locations
                or extraction_paths.census_bds_manifest_paths
            ),
            bls_laus_manifest_paths=(
                extraction_paths.bls_laus_manifest_locations
                or extraction_paths.bls_laus_manifest_paths
            ),
            validation_result_paths=[
                validation_output.artifact_location or validation_output.local_path
            ],
            storage_integration=config.storage_integration,
        )
    finally:
        connection.close()
