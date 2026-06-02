"""Raw manifest and raw artifact rule checks."""

from __future__ import annotations

from pathlib import Path

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    ArtifactReader,
    RawArtifactInspection,
    artifact_exists,
    artifact_uri,
)
from pipelines.utils.source_resources import SourceIdentity
from pipelines.utils.manifest import (
    REQUIRED_MANIFEST_FIELDS,
    normalize_manifest_storage_fields,
)
from pipelines.validation.raw_validation_check_catalog import (
    RAW_ARTIFACT_IDENTITY,
    RAW_CHECKSUM_GENERATED,
    RAW_CLOUD_MANIFEST_STORAGE,
    RAW_COLUMN_COUNT_CAPTURED,
    RAW_FILE_EXISTS,
    RAW_FILE_SIZE_POSITIVE,
    RAW_MANIFEST_CREATED,
    RAW_MANIFEST_SOURCE_IDENTITY,
    RAW_REQUIRED_MANIFEST_RESOURCE,
    RAW_REQUIRED_METADATA,
    RAW_ROW_COUNT_CAPTURED,
    RAW_SCHEMA_HASH_GENERATED,
)
from pipelines.validation.raw_validation_models import RawManifest
from pipelines.validation.validation_result import (
    ValidationResult,
    make_manifest_validation_result as _result,
    make_pipeline_validation_result,
)


def check_raw_artifact(
    manifest: RawManifest,
    *,
    inspection: RawArtifactInspection,
) -> list[ValidationResult]:
    """Validate raw file existence, size, and checksum for one manifest."""
    return [
        _check_raw_file_exists(manifest, inspection),
        _check_raw_file_size(manifest, inspection),
        _check_checksum(manifest, inspection),
    ]


def check_raw_manifest_fields(manifest: RawManifest) -> list[ValidationResult]:
    """Validate required manifest metadata and count/hash fields."""
    return [
        _check_required_metadata(manifest),
        _check_row_count(manifest),
        _check_schema_hash(manifest),
        _check_column_count(manifest),
    ]


def check_raw_manifest_artifact_rules(
    manifest: RawManifest,
    *,
    inspection: RawArtifactInspection,
    manifest_reference: Path | str | ArtifactLocation,
    manifest_artifact_reader: ArtifactReader,
) -> list[ValidationResult]:
    """Run manifest field checks plus raw artifact and manifest-file checks."""
    return [
        *check_raw_artifact(manifest, inspection=inspection),
        check_manifest_created(
            manifest,
            manifest_reference,
            manifest_artifact_reader,
        ),
        *check_raw_manifest_fields(manifest),
    ]


def check_manifest_identity_and_route_rules(
    manifest: RawManifest,
    *,
    expected_identity: SourceIdentity,
    is_cloud_route: bool,
) -> list[ValidationResult]:
    """Validate source identity and cloud-only storage requirements."""
    validation_results = [
        check_manifest_source_identity(
            manifest,
            expected_identity=expected_identity,
        )
    ]
    if is_cloud_route:
        validation_results.extend(
            [
                check_manifest_raw_uri_required(manifest),
                check_cloud_manifest_storage(manifest),
            ]
        )
    return validation_results


def check_required_manifest_resource(
    manifests: list[RawManifest],
    *,
    resource_name: str,
    pipeline_run_id: str,
    source_identity: SourceIdentity,
) -> ValidationResult:
    """Validate that a required resource name appears in loaded manifests."""
    resource_names = sorted(
        str(manifest.get("resource_name")) for manifest in manifests
    )
    return make_pipeline_validation_result(
        pipeline_run_id=pipeline_run_id,
        check_definition=RAW_REQUIRED_MANIFEST_RESOURCE,
        source_system=source_identity.source_system,
        source_dataset=source_identity.dataset_name,
        source_resource_name=resource_name,
        passed=resource_name in resource_names,
        expected_value=resource_name,
        observed_value={"resource_names": resource_names},
        failed_message="Required raw manifest resource is missing.",
    )


def check_manifest_source_identity(
    manifest: RawManifest,
    *,
    expected_identity: SourceIdentity,
) -> ValidationResult:
    """Validate that manifest source identity matches source config."""
    observed_identity = {
        "source_system": str(manifest.get("source_system", "unknown")),
        "dataset_name": str(manifest.get("dataset_name", "unknown")),
    }
    expected_value = {
        "source_system": expected_identity.source_system,
        "dataset_name": expected_identity.dataset_name,
    }
    return _result(
        manifest=manifest,
        check_definition=RAW_MANIFEST_SOURCE_IDENTITY,
        passed=observed_identity == expected_value,
        expected_value=expected_value,
        observed_value=observed_identity,
        failed_message="Manifest source identity does not match source config.",
    )


def check_cloud_manifest_storage(manifest: RawManifest) -> ValidationResult:
    """Validate that cloud-route manifests point to S3-backed raw artifacts."""
    storage_backend = str(manifest.get("storage_backend", "")).lower()
    raw_uri = str(manifest.get("raw_uri") or "")
    return _result(
        manifest=manifest,
        check_definition=RAW_CLOUD_MANIFEST_STORAGE,
        passed=storage_backend == "s3" and raw_uri.startswith("s3://"),
        expected_value={"storage_backend": "s3", "raw_uri_prefix": "s3://"},
        observed_value={
            "storage_backend": storage_backend or None,
            "raw_uri": raw_uri or None,
        },
        failed_message="Cloud route requires S3-backed raw manifests.",
    )


def check_manifest_raw_uri_required(manifest: RawManifest) -> ValidationResult:
    """Validate that the manifest carries a route-neutral raw artifact URI."""
    raw_uri = manifest.get("raw_uri")
    return _result(
        manifest=manifest,
        check_definition=RAW_ARTIFACT_IDENTITY,
        passed=isinstance(raw_uri, str) and bool(raw_uri.strip()),
        expected_value="raw_uri populated",
        observed_value=raw_uri,
        failed_message="Manifest is missing required raw_uri identity.",
    )


def check_manifest_created(
    manifest: RawManifest,
    manifest_reference: Path | str | ArtifactLocation,
    manifest_artifact_reader: ArtifactReader,
) -> ValidationResult:
    """Validate that the manifest artifact itself can be found."""
    manifest_exists = artifact_exists(manifest_reference, manifest_artifact_reader)
    return _result(
        manifest=manifest,
        check_definition=RAW_MANIFEST_CREATED,
        passed=manifest_exists,
        expected_value="manifest file exists",
        observed_value=artifact_uri(manifest_reference),
        failed_message="Manifest file is missing.",
    )


def _check_raw_file_exists(
    manifest: RawManifest,
    inspection: RawArtifactInspection,
) -> ValidationResult:
    """Build the raw file existence validation result."""
    raw_uri = _raw_artifact_uri(manifest)
    return _result(
        manifest=manifest,
        check_definition=RAW_FILE_EXISTS,
        passed=inspection.exists,
        expected_value="file exists",
        observed_value=raw_uri,
        failed_message="Raw file is missing.",
    )


def _check_raw_file_size(
    manifest: RawManifest,
    inspection: RawArtifactInspection,
) -> ValidationResult:
    """Build the positive raw file size validation result."""
    observed_size = inspection.size_bytes
    return _result(
        manifest=manifest,
        check_definition=RAW_FILE_SIZE_POSITIVE,
        passed=observed_size > 0,
        expected_value="file size > 0",
        observed_value=observed_size,
        failed_message="Raw file is empty or unavailable.",
    )


def _check_checksum(
    manifest: RawManifest,
    inspection: RawArtifactInspection,
) -> ValidationResult:
    """Build the raw artifact checksum validation result."""
    expected_checksum = str(manifest.get("sha256_checksum", ""))
    observed_checksum = inspection.sha256_checksum
    return _result(
        manifest=manifest,
        check_definition=RAW_CHECKSUM_GENERATED,
        passed=bool(expected_checksum) and observed_checksum == expected_checksum,
        expected_value=expected_checksum,
        observed_value=observed_checksum,
        failed_message="Raw file checksum is missing or does not match.",
    )


def _raw_artifact_uri(manifest: RawManifest) -> str:
    """Return the best available route-neutral raw artifact URI."""
    normalized_manifest = normalize_manifest_storage_fields(manifest)
    # Older local manifests may only have local_raw_path; cloud manifests should
    # carry raw_uri/s3_raw_uri. The result uses whichever identity exists.
    return str(
        normalized_manifest.get("raw_uri")
        or normalized_manifest.get("local_raw_path")
        or normalized_manifest.get("s3_raw_uri")
        or ""
    )


def _check_required_metadata(manifest: RawManifest) -> ValidationResult:
    """Build the required manifest metadata validation result."""
    normalized_manifest = normalize_manifest_storage_fields(manifest)
    missing_fields = sorted(REQUIRED_MANIFEST_FIELDS - set(normalized_manifest))
    return _result(
        manifest=normalized_manifest,
        check_definition=RAW_REQUIRED_METADATA,
        passed=missing_fields == [],
        expected_value=sorted(REQUIRED_MANIFEST_FIELDS),
        observed_value={"missing_fields": missing_fields},
        failed_message="Manifest is missing required metadata fields.",
    )


def _check_row_count(manifest: RawManifest) -> ValidationResult:
    """Build the row-count metadata validation result."""
    row_count = manifest.get("row_count")
    return _result(
        manifest=manifest,
        check_definition=RAW_ROW_COUNT_CAPTURED,
        passed=isinstance(row_count, int) and row_count >= 0,
        expected_value="row_count is a non-negative integer",
        observed_value=row_count,
        failed_message="Manifest row count is missing or invalid.",
    )


def _check_schema_hash(manifest: RawManifest) -> ValidationResult:
    """Build the schema-hash metadata validation result."""
    schema_hash = manifest.get("schema_hash")
    return _result(
        manifest=manifest,
        check_definition=RAW_SCHEMA_HASH_GENERATED,
        passed=bool(schema_hash),
        expected_value="schema_hash populated",
        observed_value=schema_hash,
        failed_message="Manifest schema hash is missing.",
    )


def _check_column_count(manifest: RawManifest) -> ValidationResult:
    """Build the optional column-count metadata validation result."""
    column_count = manifest.get("column_count")
    return _result(
        manifest=manifest,
        check_definition=RAW_COLUMN_COUNT_CAPTURED,
        passed=column_count is None
        or (isinstance(column_count, int) and column_count >= 0),
        expected_value="column_count omitted or non-negative integer",
        observed_value=column_count,
        failed_message="Manifest column count is invalid.",
    )
