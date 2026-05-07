from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipelines.utils.hashing import calculate_sha256
from pipelines.utils.manifest import REQUIRED_MANIFEST_FIELDS
from pipelines.validation.validation_result import (
    ValidationResult,
    make_validation_result,
)


def check_raw_manifest(manifest_path: Path | str) -> list[ValidationResult]:
    resolved_manifest_path = Path(manifest_path)
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
        _check_raw_file_exists(manifest),
        _check_raw_file_size(manifest),
        _check_checksum(manifest),
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


def _check_raw_file_exists(manifest: dict[str, Any]) -> ValidationResult:
    raw_path = Path(str(manifest.get("local_raw_path", "")))
    return _result(
        manifest=manifest,
        validation_check_id="RAW_001",
        check_name="Raw file exists",
        check_type="completeness",
        severity="fail",
        passed=raw_path.is_file(),
        expected_value="file exists",
        observed_value=str(raw_path),
        failed_message="Raw file is missing.",
    )


def _check_raw_file_size(manifest: dict[str, Any]) -> ValidationResult:
    raw_path = Path(str(manifest.get("local_raw_path", "")))
    observed_size = raw_path.stat().st_size if raw_path.is_file() else 0
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


def _check_checksum(manifest: dict[str, Any]) -> ValidationResult:
    raw_path = Path(str(manifest.get("local_raw_path", "")))
    expected_checksum = str(manifest.get("sha256_checksum", ""))
    observed_checksum = calculate_sha256(raw_path) if raw_path.is_file() else None
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
    missing_fields = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    return _result(
        manifest=manifest,
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
