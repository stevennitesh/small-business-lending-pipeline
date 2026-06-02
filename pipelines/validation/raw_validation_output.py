"""Persist raw validation results locally and optionally to artifact storage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    ArtifactReader,
    ArtifactReference,
    artifact_exists,
    artifact_store_for_route,
    artifact_uri,
)
from pipelines.validation.raw_validation_check_catalog import (
    RAW_VALIDATION_RESULT_CREATED,
)
from pipelines.validation.raw_validation_models import RawManifest
from pipelines.validation.raw_validation_resources import (
    VALIDATION_RESULTS_DATASET_NAME,
    VALIDATION_RESULTS_FILENAME,
    VALIDATION_RESULTS_RESOURCE_NAME,
    VALIDATION_RESULTS_SOURCE_SYSTEM,
)
from pipelines.validation.validation_result import (
    ValidationResult,
    make_pipeline_validation_result,
)
from pipelines.validation.validation_result_io import (
    validation_results_to_json_bytes,
    write_validation_results,
)


class ValidationArtifactStore(Protocol):
    """Minimal artifact-store protocol needed to write validation outputs."""

    def location(
        self,
        *,
        prefix: str,
        source_system: str,
        dataset_name: str,
        resource_name: str,
        ingestion_date: str,
        pipeline_run_id: str,
        filename: str,
    ) -> ArtifactLocation: ...

    def write_bytes(
        self,
        location: ArtifactLocation,
        payload: bytes,
    ) -> None: ...


@dataclass(frozen=True)
class _ValidationOutputDestination:
    """Resolved local and optional remote destination for validation results."""

    local_path: Path
    artifact_location: ArtifactLocation | None = None
    artifact_store: ValidationArtifactStore | None = None


@dataclass(frozen=True)
class ValidationOutputWrite:
    """Output metadata returned after validation results are written."""

    local_path: Path
    artifact_location: ArtifactLocation | None
    validation_results: list[ValidationResult]


@dataclass(frozen=True)
class ValidationOutputWriteRequest:
    """Inputs needed to choose and write validation output destinations."""

    validation_results: list[ValidationResult]
    manifests: list[RawManifest]
    validation_path: Path
    pipeline_run_id: str
    is_cloud_route: bool
    data_root: Path
    run_started_at_utc: str
    bucket: str | None
    artifact_reader: ArtifactReader
    artifact_store: ValidationArtifactStore | None = None


def write_validation_output_for_route(
    request: ValidationOutputWriteRequest,
) -> ValidationOutputWrite:
    """Write validation output for local or cloud route and append self-check."""
    destination = _validation_output_destination(
        request.manifests,
        validation_path=request.validation_path,
        pipeline_run_id=request.pipeline_run_id,
        is_cloud_route=request.is_cloud_route,
        data_root=request.data_root,
        run_started_at_utc=request.run_started_at_utc,
        bucket=request.bucket,
        artifact_store=request.artifact_store,
    )
    final_validation_results = _write_validation_output_with_self_check(
        request.validation_results,
        pipeline_run_id=request.pipeline_run_id,
        destination=destination,
        artifact_reader=request.artifact_reader,
    )
    return ValidationOutputWrite(
        local_path=destination.local_path,
        artifact_location=destination.artifact_location,
        validation_results=final_validation_results,
    )


def _validation_output_destination(
    manifests: list[RawManifest],
    *,
    validation_path: Path,
    pipeline_run_id: str,
    is_cloud_route: bool,
    data_root: Path,
    run_started_at_utc: str,
    bucket: str | None,
    artifact_store: ValidationArtifactStore | None = None,
) -> _ValidationOutputDestination:
    """Resolve local path plus optional cloud artifact destination."""
    if not is_cloud_route:
        return _ValidationOutputDestination(local_path=validation_path)
    ingestion_date = (
        str(manifests[0]["ingestion_date"]) if manifests else run_started_at_utc[:10]
    )
    store = _validation_artifact_store(
        is_cloud_route=is_cloud_route,
        data_root=data_root,
        bucket=bucket,
        artifact_store=artifact_store,
    )
    artifact_location = store.location(
        prefix="validation",
        source_system=VALIDATION_RESULTS_SOURCE_SYSTEM,
        dataset_name=VALIDATION_RESULTS_DATASET_NAME,
        resource_name=VALIDATION_RESULTS_RESOURCE_NAME,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        filename=VALIDATION_RESULTS_FILENAME,
    )
    return _ValidationOutputDestination(
        local_path=validation_path,
        artifact_location=artifact_location,
        artifact_store=store,
    )


def _write_validation_output(
    validation_results: list[ValidationResult],
    *,
    destination: _ValidationOutputDestination,
) -> None:
    """Write validation results to the resolved destination."""
    write_validation_results(validation_results, destination.local_path)
    if destination.artifact_location is None:
        return
    if destination.artifact_store is None:
        raise ValueError(
            "Validation artifact destination is missing its artifact store."
        )
    destination.artifact_store.write_bytes(
        destination.artifact_location,
        validation_results_to_json_bytes(validation_results),
    )


def _write_validation_output_with_self_check(
    validation_results: list[ValidationResult],
    *,
    pipeline_run_id: str,
    destination: _ValidationOutputDestination,
    artifact_reader: ArtifactReader,
) -> list[ValidationResult]:
    """Write once, validate output existence, then rewrite with that check included."""
    _write_validation_output(
        validation_results,
        destination=destination,
    )
    final_validation_results = [
        *validation_results,
        check_validation_output_created(
            destination.artifact_location or destination.local_path,
            pipeline_run_id=pipeline_run_id,
            artifact_reader=artifact_reader,
        ),
    ]
    _write_validation_output(
        final_validation_results,
        destination=destination,
    )
    return final_validation_results


def check_validation_output_created(
    output_reference: ArtifactReference,
    *,
    pipeline_run_id: str,
    artifact_reader: ArtifactReader | None = None,
) -> ValidationResult:
    """Validate that the validation result artifact was created."""
    output_exists = artifact_exists(
        output_reference,
        artifact_reader or ArtifactReader(),
    )
    return make_pipeline_validation_result(
        pipeline_run_id=pipeline_run_id,
        check_definition=RAW_VALIDATION_RESULT_CREATED,
        source_system=VALIDATION_RESULTS_SOURCE_SYSTEM,
        source_dataset=VALIDATION_RESULTS_DATASET_NAME,
        source_resource_name=VALIDATION_RESULTS_RESOURCE_NAME,
        passed=output_exists,
        expected_value="validation output file exists",
        observed_value=artifact_uri(output_reference),
        failed_message="Validation output file is missing.",
    )


def _validation_artifact_store(
    *,
    is_cloud_route: bool,
    data_root: Path,
    bucket: str | None,
    artifact_store: ValidationArtifactStore | None = None,
) -> ValidationArtifactStore:
    """Return an injected validation artifact store or build one for the route."""
    if artifact_store is not None:
        return artifact_store
    resolved_bucket = bucket or "local-validation"
    return artifact_store_for_route(
        cloud_route=is_cloud_route,
        data_root=data_root,
        bucket=resolved_bucket,
    )
