"""Flow adapter for raw validation runner inputs and artifact routing."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from pipelines.flows.extraction_manifests import ExtractionPaths
from pipelines.flows.run_models import (
    LocalRunContext,
)
from pipelines.flows.run_setup import resolve_s3_bucket
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    ArtifactReader,
    RawArtifactReader,
    artifact_reader_for_route,
    raw_artifact_reader_for_route,
)
from pipelines.utils.config import ProjectConfig
from pipelines.validation.raw_validation_models import (
    RawValidationInput,
    RawValidationOutput,
)
from pipelines.validation.raw_validation_output import ValidationArtifactStore
from pipelines.validation.raw_validation_resources import VALIDATION_RESULTS_FILENAME
from pipelines.validation.raw_validation_runner import validate_raw_outputs


ArtifactReaderFactory = Callable[[LocalRunContext], ArtifactReader]
RawArtifactReaderFactory = Callable[[LocalRunContext], RawArtifactReader]
ValidationArtifactStoreFactory = Callable[
    [LocalRunContext, str],
    ValidationArtifactStore,
]
BucketResolver = Callable[[LocalRunContext], str | None]


def validate_raw_outputs_for_flow(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
    project_config: ProjectConfig,
    *,
    artifact_reader_factory: ArtifactReaderFactory | None = None,
    raw_artifact_reader_factory: RawArtifactReaderFactory | None = None,
    artifact_store_factory: ValidationArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> RawValidationOutput:
    """Build raw-validation inputs from flow context and extraction paths."""
    validation_bucket = (
        (s3_bucket_resolver or resolve_s3_bucket)(context) or "local-validation"
    )
    validation_artifact_store = (
        artifact_store_factory(context, validation_bucket)
        if artifact_store_factory is not None
        else None
    )
    return validate_raw_outputs(
        RawValidationInput(
            pipeline_run_id=context.pipeline_run_id,
            extract_mode=context.extract_mode,
            is_cloud_route=context.is_cloud_route,
            data_root=context.data_root,
            run_started_at_utc=context.run_started_at_utc,
            validation_path=context.run_validation_dir / VALIDATION_RESULTS_FILENAME,
            manifest_references=manifest_references_for_validation(
                context,
                extraction_paths,
            ),
            s3_bucket=validation_bucket,
        ),
        project_config,
        manifest_reader=(artifact_reader_factory or default_artifact_reader)(context),
        raw_artifact_reader=(
            raw_artifact_reader_factory or default_raw_artifact_reader
        )(context),
        validation_artifact_store=validation_artifact_store,
    )


def default_artifact_reader(
    context: LocalRunContext,
    s3_client=None,
) -> ArtifactReader:
    """Create the route-specific reader for manifest and validation artifacts."""
    return artifact_reader_for_route(
        cloud_route=context.is_cloud_route,
        s3_client=s3_client,
    )


def default_raw_artifact_reader(
    context: LocalRunContext,
    s3_client=None,
) -> RawArtifactReader:
    """Create the route-specific reader for raw extraction artifacts."""
    return raw_artifact_reader_for_route(
        cloud_route=context.is_cloud_route,
        s3_client=s3_client,
    )


def manifest_references_for_validation(
    context: LocalRunContext,
    extraction_paths: ExtractionPaths,
) -> tuple[Path | ArtifactLocation, ...]:
    """Choose manifest references that validation should read for this route."""
    return extraction_paths.manifest_references_for_validation(
        cloud_route=context.is_cloud_route,
    )
