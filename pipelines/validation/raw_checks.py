from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipelines.utils.config import SourceIdentity
from pipelines.utils.manifest import (
    REQUIRED_MANIFEST_FIELDS,
    normalize_manifest_storage_fields,
)
from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.validation.validation_result import (
    ValidationResult,
    make_validation_result,
)


def check_raw_manifest(
    manifest_path: Path | str,
    *,
    artifact_reader: RawArtifactReader | None = None,
) -> list[ValidationResult]:
    resolved_manifest_path = Path(manifest_path)
    reader = artifact_reader or RawArtifactReader()
    if not resolved_manifest_path.is_file():
        return [
            _result(
                manifest={},
                validation_check_id="RAW_005",
                check_name="Manifest created",
                check_type="lineage",
                severity="fail",
                passed=False,
                expected_value="manifest file exists",
                observed_value=str(resolved_manifest_path),
                failed_message="Manifest file is missing.",
            )
        ]

    manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    results = [
        _check_raw_file_exists(manifest, reader),
        _check_raw_file_size(manifest, reader),
        _check_checksum(manifest, reader),
        _check_manifest_created(manifest, resolved_manifest_path),
        _check_required_metadata(manifest),
        _check_row_count(manifest),
        _check_schema_hash(manifest),
        _check_column_count(manifest),
    ]
    return results


def check_validation_output_created(
    output_path: Path | str,
    *,
    pipeline_run_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
) -> ValidationResult:
    resolved_output_path = Path(output_path)
    return make_validation_result(
        pipeline_run_id=pipeline_run_id,
        validation_check_id="RAW_009",
        validation_scope="raw",
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name="Validation result created",
        check_type="lineage",
        severity="fail",
        passed=resolved_output_path.is_file(),
        expected_value="validation output file exists",
        observed_value=str(resolved_output_path),
        passed_message="Validation output file exists.",
        failed_message="Validation output file is missing.",
    )


def check_required_manifest_resource(
    manifests: list[dict[str, Any]],
    *,
    resource_name: str,
    pipeline_run_id: str,
    source_identity: SourceIdentity,
) -> ValidationResult:
    resource_names = sorted(str(manifest.get("resource_name")) for manifest in manifests)
    return make_validation_result(
        pipeline_run_id=pipeline_run_id,
        validation_check_id="RAW_011",
        validation_scope="raw",
        source_system=source_identity.source_system,
        source_dataset=source_identity.dataset_name,
        source_resource_name=resource_name,
        check_name="Required raw manifest resource present",
        check_type="lineage",
        severity="fail",
        passed=resource_name in resource_names,
        expected_value=resource_name,
        observed_value={"resource_names": resource_names},
        passed_message="Required raw manifest resource is present.",
        failed_message="Required raw manifest resource is missing.",
    )


def check_manifest_source_identity(
    manifest: dict[str, Any],
    *,
    expected_identity: SourceIdentity,
) -> ValidationResult:
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
        validation_check_id="RAW_010",
        check_name="Manifest source identity matches config",
        check_type="lineage",
        severity="fail",
        passed=observed_identity == expected_value,
        expected_value=expected_value,
        observed_value=observed_identity,
        failed_message="Manifest source identity does not match source config.",
    )


def check_cloud_manifest_storage(manifest: dict[str, Any]) -> ValidationResult:
    storage_backend = str(manifest.get("storage_backend", "")).lower()
    raw_uri = str(manifest.get("raw_uri") or "")
    return _result(
        manifest=manifest,
        validation_check_id="RAW_012",
        check_name="Cloud raw manifest is S3-backed",
        check_type="lineage",
        severity="fail",
        passed=storage_backend == "s3" and raw_uri.startswith("s3://"),
        expected_value={"storage_backend": "s3", "raw_uri_prefix": "s3://"},
        observed_value={
            "storage_backend": storage_backend or None,
            "raw_uri": raw_uri or None,
        },
        failed_message="Cloud route requires S3-backed raw manifests.",
    )


def check_manifest_raw_uri_required(manifest: dict[str, Any]) -> ValidationResult:
    raw_uri = manifest.get("raw_uri")
    return _result(
        manifest=manifest,
        validation_check_id="RAW_013",
        check_name="Raw artifact identity populated",
        check_type="lineage",
        severity="fail",
        passed=isinstance(raw_uri, str) and bool(raw_uri.strip()),
        expected_value="raw_uri populated",
        observed_value=raw_uri,
        failed_message="Manifest is missing required raw_uri identity.",
    )


def _check_raw_file_exists(
    manifest: dict[str, Any],
    artifact_reader: RawArtifactReader,
) -> ValidationResult:
    raw_uri = _raw_artifact_uri(manifest)
    return _result(
        manifest=manifest,
        validation_check_id="RAW_001",
        check_name="Raw file exists",
        check_type="completeness",
        severity="fail",
        passed=artifact_reader.exists(manifest),
        expected_value="file exists",
        observed_value=raw_uri,
        failed_message="Raw file is missing.",
    )


def _check_raw_file_size(
    manifest: dict[str, Any],
    artifact_reader: RawArtifactReader,
) -> ValidationResult:
    observed_size = artifact_reader.size_bytes(manifest)
    return _result(
        manifest=manifest,
        validation_check_id="RAW_002",
        check_name="Raw file size is positive",
        check_type="completeness",
        severity="fail",
        passed=observed_size > 0,
        expected_value="file size > 0",
        observed_value=observed_size,
        failed_message="Raw file is empty or unavailable.",
    )


def _check_checksum(
    manifest: dict[str, Any],
    artifact_reader: RawArtifactReader,
) -> ValidationResult:
    expected_checksum = str(manifest.get("sha256_checksum", ""))
    observed_checksum = artifact_reader.sha256(manifest)
    return _result(
        manifest=manifest,
        validation_check_id="RAW_003",
        check_name="SHA-256 checksum generated",
        check_type="lineage",
        severity="fail",
        passed=bool(expected_checksum) and observed_checksum == expected_checksum,
        expected_value=expected_checksum,
        observed_value=observed_checksum,
        failed_message="Raw file checksum is missing or does not match.",
    )


def _check_manifest_created(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> ValidationResult:
    return _result(
        manifest=manifest,
        validation_check_id="RAW_004",
        check_name="Manifest created",
        check_type="lineage",
        severity="fail",
        passed=manifest_path.is_file(),
        expected_value="manifest file exists",
        observed_value=str(manifest_path),
        failed_message="Manifest file is missing.",
    )


def _check_required_metadata(manifest: dict[str, Any]) -> ValidationResult:
    normalized_manifest = normalize_manifest_storage_fields(manifest)
    missing_fields = sorted(REQUIRED_MANIFEST_FIELDS - set(normalized_manifest))
    return _result(
        manifest=normalized_manifest,
        validation_check_id="RAW_005",
        check_name="Required metadata populated",
        check_type="lineage",
        severity="fail",
        passed=missing_fields == [],
        expected_value=sorted(REQUIRED_MANIFEST_FIELDS),
        observed_value={"missing_fields": missing_fields},
        failed_message="Manifest is missing required metadata fields.",
    )


def _check_row_count(manifest: dict[str, Any]) -> ValidationResult:
    row_count = manifest.get("row_count")
    return _result(
        manifest=manifest,
        validation_check_id="RAW_006",
        check_name="Row count captured",
        check_type="completeness",
        severity="fail",
        passed=isinstance(row_count, int) and row_count >= 0,
        expected_value="row_count is a non-negative integer",
        observed_value=row_count,
        failed_message="Manifest row count is missing or invalid.",
    )


def _check_schema_hash(manifest: dict[str, Any]) -> ValidationResult:
    schema_hash = manifest.get("schema_hash")
    return _result(
        manifest=manifest,
        validation_check_id="RAW_007",
        check_name="Schema hash generated",
        check_type="lineage",
        severity="warning",
        passed=bool(schema_hash),
        expected_value="schema_hash populated",
        observed_value=schema_hash,
        failed_message="Manifest schema hash is missing.",
    )


def _check_column_count(manifest: dict[str, Any]) -> ValidationResult:
    column_count = manifest.get("column_count")
    return _result(
        manifest=manifest,
        validation_check_id="RAW_008",
        check_name="Column count captured",
        check_type="completeness",
        severity="warning",
        passed=column_count is None or (isinstance(column_count, int) and column_count >= 0),
        expected_value="column_count omitted or non-negative integer",
        observed_value=column_count,
        failed_message="Manifest column count is invalid.",
    )


def _raw_artifact_uri(manifest: dict[str, Any]) -> str:
    normalized_manifest = normalize_manifest_storage_fields(manifest)
    return str(
        normalized_manifest.get("raw_uri")
        or normalized_manifest.get("local_raw_path")
        or normalized_manifest.get("s3_raw_uri")
        or ""
    )


def _result(
    *,
    manifest: dict[str, Any],
    validation_check_id: str,
    check_name: str,
    check_type: str,
    severity: str,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
) -> ValidationResult:
    return make_validation_result(
        pipeline_run_id=str(manifest.get("pipeline_run_id", "unknown")),
        validation_check_id=validation_check_id,
        source_system=str(manifest.get("source_system", "unknown")),
        source_dataset=str(manifest.get("dataset_name", "unknown")),
        source_resource_name=str(manifest.get("resource_name", "unknown")),
        check_name=check_name,
        check_type=check_type,
        severity=severity,
        passed=passed,
        expected_value=expected_value,
        observed_value=observed_value,
        passed_message=f"{check_name} check passed.",
        failed_message=failed_message,
    )
