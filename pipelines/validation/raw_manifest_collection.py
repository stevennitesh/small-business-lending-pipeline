"""Load raw manifest references into validation-ready manifest objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    ArtifactReader,
    ArtifactReference,
    artifact_uri,
    read_artifact_text,
)
from pipelines.validation.raw_validation_check_catalog import (
    RAW_MANIFEST_CREATED,
    RAW_MANIFEST_READABLE_JSON,
    ValidationCheckDefinition,
)
from pipelines.validation.raw_validation_models import (
    LoadedManifestReference,
    RawManifest,
)
from pipelines.validation.validation_result import (
    ValidationResult,
    make_pipeline_validation_result,
)


@dataclass(frozen=True)
class ManifestLoadResult:
    """Result of attempting to load one manifest reference."""

    loaded_manifest: LoadedManifestReference | None = None
    failure: ValidationResult | None = None

    @property
    def loaded_manifest_or_raise(self) -> LoadedManifestReference:
        """Return the loaded manifest or raise when this result is a failure."""
        if self.loaded_manifest is None:
            raise AssertionError("Manifest load result has no loaded manifest.")
        return self.loaded_manifest


def load_manifests_for_validation(
    pipeline_run_id: str,
    manifest_references: tuple[Path | ArtifactLocation, ...],
    manifest_artifact_reader: ArtifactReader,
) -> tuple[list[LoadedManifestReference], list[ValidationResult]]:
    """Load all manifest references, returning loaded manifests and failures."""
    loaded_manifest_references: list[LoadedManifestReference] = []
    validation_results: list[ValidationResult] = []
    for reference in manifest_references:
        load_result = load_manifest_for_validation(
            pipeline_run_id,
            reference,
            manifest_artifact_reader,
        )
        if load_result.failure is not None:
            validation_results.append(load_result.failure)
            continue
        loaded_manifest_references.append(load_result.loaded_manifest_or_raise)
    return loaded_manifest_references, validation_results


def load_manifest_for_validation(
    pipeline_run_id: str,
    reference: ArtifactReference,
    manifest_artifact_reader: ArtifactReader,
) -> ManifestLoadResult:
    """Read and parse one manifest reference for validation."""
    try:
        manifest_text = read_artifact_text(reference, manifest_artifact_reader)
    except (BotoCoreError, ClientError, OSError):
        return ManifestLoadResult(
            failure=_manifest_reference_failure(
                pipeline_run_id,
                reference,
                check_definition=RAW_MANIFEST_CREATED,
                expected_value="manifest file exists",
                failed_message="Manifest file is missing.",
            )
        )

    try:
        manifest: RawManifest = json.loads(manifest_text)
    except json.JSONDecodeError:
        return ManifestLoadResult(
            failure=_manifest_reference_failure(
                pipeline_run_id,
                reference,
                check_definition=RAW_MANIFEST_READABLE_JSON,
                expected_value="manifest file contains valid JSON",
                failed_message="Manifest file is not valid JSON.",
            )
        )

    return ManifestLoadResult(
        loaded_manifest=LoadedManifestReference(
            reference=_loaded_manifest_reference(reference),
            manifest=manifest,
        )
    )


def _manifest_reference_failure(
    pipeline_run_id: str,
    reference: ArtifactReference,
    *,
    check_definition: ValidationCheckDefinition,
    expected_value: str,
    failed_message: str,
) -> ValidationResult:
    """Build a validation failure for an unreadable manifest reference."""
    return make_pipeline_validation_result(
        pipeline_run_id=pipeline_run_id,
        check_definition=check_definition,
        source_resource_name="manifest_reference",
        passed=False,
        expected_value=expected_value,
        observed_value=artifact_uri(reference),
        failed_message=failed_message,
    )


def _loaded_manifest_reference(reference: ArtifactReference) -> Path | ArtifactLocation:
    """Normalize a manifest reference into the loaded-reference shape."""
    if isinstance(reference, ArtifactLocation):
        return reference
    return Path(reference)
