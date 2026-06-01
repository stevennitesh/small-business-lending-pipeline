from __future__ import annotations

from dataclasses import dataclass

from pipelines.storage.raw_artifacts import (
    ArtifactReader,
    RawArtifactReader,
    artifact_reader_for_route,
    raw_artifact_reader_for_route,
)
from pipelines.utils.config import ProjectConfig
from pipelines.validation.raw_manifest_artifact_validation import (
    raw_file_exists_resource_names,
    validate_loaded_manifest_artifacts,
    validate_manifest_identities_and_storage,
)
from pipelines.validation.raw_manifest_collection import (
    load_manifests_for_validation,
)
from pipelines.validation.raw_validation_models import (
    RawManifestIndex,
    RawManifest,
    RawValidationInput,
    RawValidationOutput,
)
from pipelines.validation.raw_validation_output import (
    ValidationArtifactStore,
    ValidationOutputWriteRequest,
    write_validation_output_for_route,
)
from pipelines.validation.raw_validation_sources import validate_source_outputs
from pipelines.validation.validation_failures import (
    assert_no_blocking_failures,
)
from pipelines.validation.validation_result import ValidationResult


@dataclass(frozen=True)
class RawValidationCollection:
    validation_results: list[ValidationResult]
    manifests: list[RawManifest]


def validate_raw_outputs(
    validation_input: RawValidationInput,
    project_config: ProjectConfig,
    *,
    manifest_reader: ArtifactReader | None = None,
    raw_artifact_reader: RawArtifactReader | None = None,
    validation_artifact_store: ValidationArtifactStore | None = None,
) -> RawValidationOutput:
    resolved_manifest_reader = manifest_reader or artifact_reader_for_route(
        cloud_route=validation_input.is_cloud_route,
    )
    resolved_raw_artifact_reader = raw_artifact_reader or raw_artifact_reader_for_route(
        cloud_route=validation_input.is_cloud_route,
    )
    collection = collect_raw_validation_results(
        validation_input,
        project_config,
        manifest_reader=resolved_manifest_reader,
        raw_artifact_reader=resolved_raw_artifact_reader,
    )
    validation_results = collection.validation_results
    manifests = collection.manifests

    output_write = write_validation_output_for_route(
        ValidationOutputWriteRequest(
            validation_results=validation_results,
            manifests=manifests,
            validation_path=validation_input.validation_path,
            pipeline_run_id=validation_input.pipeline_run_id,
            is_cloud_route=validation_input.is_cloud_route,
            data_root=validation_input.data_root,
            run_started_at_utc=validation_input.run_started_at_utc,
            bucket=validation_input.s3_bucket,
            artifact_reader=resolved_manifest_reader,
            artifact_store=validation_artifact_store,
        )
    )
    assert_no_blocking_failures(output_write.validation_results)
    return RawValidationOutput(
        local_path=output_write.local_path,
        artifact_location=output_write.artifact_location,
    )


def collect_raw_validation_results(
    validation_input: RawValidationInput,
    project_config: ProjectConfig,
    *,
    manifest_reader: ArtifactReader,
    raw_artifact_reader: RawArtifactReader,
) -> RawValidationCollection:
    validation_results: list[ValidationResult] = []
    loaded_manifest_references, manifest_load_results = load_manifests_for_validation(
        validation_input.pipeline_run_id,
        validation_input.manifest_references,
        manifest_reader,
    )
    validation_results.extend(manifest_load_results)
    manifests = [loaded.manifest for loaded in loaded_manifest_references]
    raw_manifest_results = validate_loaded_manifest_artifacts(
        loaded_manifest_references,
        manifest_reader=manifest_reader,
        raw_artifact_reader=raw_artifact_reader,
    )
    validation_results.extend(raw_manifest_results)
    raw_file_exists_names = raw_file_exists_resource_names(raw_manifest_results)
    manifest_index = RawManifestIndex.from_manifests(manifests)
    validation_results.extend(
        validate_manifest_identities_and_storage(
            manifest_index,
            project_config,
            is_cloud_route=validation_input.is_cloud_route,
        )
    )
    validation_results.extend(
        validate_source_outputs(
            manifest_index,
            project_config,
            pipeline_run_id=validation_input.pipeline_run_id,
            extract_mode=validation_input.extract_mode,
            artifact_reader=raw_artifact_reader,
            raw_file_exists_resource_names=raw_file_exists_names,
        )
    )
    return RawValidationCollection(
        validation_results=validation_results,
        manifests=manifests,
    )
