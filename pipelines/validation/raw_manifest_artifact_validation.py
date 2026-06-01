from __future__ import annotations

from pathlib import Path

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    ArtifactReader,
    RawArtifactReader,
)
from pipelines.utils.config import ProjectConfig
from pipelines.utils.source_resources import source_name_for_resource
from pipelines.validation.raw_manifest_collection import (
    load_manifest_for_validation,
)
from pipelines.validation.raw_manifest_rule_checks import (
    check_manifest_identity_and_route_rules,
    check_raw_manifest_artifact_rules,
)
from pipelines.validation.raw_validation_check_catalog import (
    RAW_FILE_EXISTS,
)
from pipelines.validation.raw_validation_models import (
    LoadedManifestReference,
    RawManifest,
    RawManifestIndex,
)
from pipelines.validation.validation_result import ValidationResult


def check_raw_manifest(
    manifest_reference: Path | str | ArtifactLocation,
    *,
    artifact_reader: RawArtifactReader | None = None,
    manifest_artifact_reader: ArtifactReader | None = None,
) -> list[ValidationResult]:
    reader = artifact_reader or RawArtifactReader()
    manifest_reader = manifest_artifact_reader or ArtifactReader()
    load_result = load_manifest_for_validation(
        "unknown",
        manifest_reference,
        manifest_reader,
    )
    if load_result.failure is not None:
        return [load_result.failure]
    loaded_manifest = load_result.loaded_manifest_or_raise

    return check_raw_manifest_artifact(
        loaded_manifest.manifest,
        manifest_reference=loaded_manifest.reference,
        artifact_reader=reader,
        manifest_artifact_reader=manifest_reader,
    )


def check_raw_manifest_artifact(
    manifest: RawManifest,
    *,
    manifest_reference: Path | str | ArtifactLocation,
    artifact_reader: RawArtifactReader | None = None,
    manifest_artifact_reader: ArtifactReader | None = None,
) -> list[ValidationResult]:
    reader = artifact_reader or RawArtifactReader()
    manifest_reader = manifest_artifact_reader or ArtifactReader()
    inspection = reader.inspect(manifest)
    return check_raw_manifest_artifact_rules(
        manifest,
        inspection=inspection,
        manifest_reference=manifest_reference,
        manifest_artifact_reader=manifest_reader,
    )


def validate_loaded_manifest_artifacts(
    loaded_manifest_references: list[LoadedManifestReference],
    *,
    manifest_reader: ArtifactReader,
    raw_artifact_reader: RawArtifactReader,
) -> list[ValidationResult]:
    validation_results: list[ValidationResult] = []
    for loaded_manifest in loaded_manifest_references:
        validation_results.extend(
            check_raw_manifest_artifact(
                loaded_manifest.manifest,
                manifest_reference=loaded_manifest.reference,
                artifact_reader=raw_artifact_reader,
                manifest_artifact_reader=manifest_reader,
            )
        )
    return validation_results


def validate_manifest_identities_and_storage(
    manifest_index: RawManifestIndex,
    project_config: ProjectConfig,
    *,
    is_cloud_route: bool,
) -> list[ValidationResult]:
    validation_results: list[ValidationResult] = []
    for manifest in manifest_index.manifests:
        validation_results.extend(
            check_manifest_identity_and_route_rules(
                manifest,
                expected_identity=project_config.source_identity(
                    source_name_for_resource(
                        str(manifest["resource_name"]),
                        project_config,
                    )
                ),
                is_cloud_route=is_cloud_route,
            )
        )
    return validation_results


def raw_file_exists_resource_names(results: list[ValidationResult]) -> set[str]:
    return {
        result.source_resource_name
        for result in results
        if result.validation_check_id == RAW_FILE_EXISTS.validation_check_id
        and result.status == "passed"
    }
