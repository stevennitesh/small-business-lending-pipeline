from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from pipelines.validation.validation_result import ValidationResult, make_validation_result


def check_sba_required_resources(
    manifests: Iterable[dict[str, Any]],
    *,
    required_resource_names: list[str],
) -> list[ValidationResult]:
    manifest_list = list(manifests)
    resources_by_name = {
        str(manifest.get("resource_name")): manifest
        for manifest in manifest_list
    }
    missing_resources = sorted(set(required_resource_names) - set(resources_by_name))
    unreadable_resources = sorted(
        resource_name
        for resource_name, manifest in resources_by_name.items()
        if resource_name in required_resource_names
        and not Path(str(manifest.get("local_raw_path", ""))).is_file()
    )
    base_manifest = manifest_list[0] if manifest_list else {}
    return [
        _source_result(
            manifest=base_manifest,
            validation_check_id="SBA_RAW_001",
            source_system="sba",
            source_dataset="7a_504_foia",
            source_resource_name="sba_required_resources",
            check_name="SBA required resources found",
            check_type="completeness",
            severity="fail",
            passed=missing_resources == [],
            expected_value=required_resource_names,
            observed_value={"missing_resources": missing_resources},
            failed_message="Required SBA resources are missing.",
        ),
        _source_result(
            manifest=base_manifest,
            validation_check_id="SBA_RAW_002",
            source_system="sba",
            source_dataset="7a_504_foia",
            source_resource_name="sba_required_resources",
            check_name="SBA required resources readable",
            check_type="validity",
            severity="fail",
            passed=unreadable_resources == [],
            expected_value="all required raw files readable",
            observed_value={"unreadable_resources": unreadable_resources},
            failed_message="One or more required SBA raw files are unreadable.",
        ),
    ]


def check_census_bds_payload(
    payload: list[list[str]],
    *,
    required_variables: tuple[str, ...],
    expected_state_count: int,
    pipeline_run_id: str,
) -> list[ValidationResult]:
    header = payload[0] if payload else []
    rows = payload[1:] if len(payload) > 1 else []
    missing_variables = sorted(set(required_variables) - set(header))
    state_count = len({row[header.index("state")] for row in rows}) if "state" in header else 0
    return [
        _source_result(
            pipeline_run_id=pipeline_run_id,
            validation_check_id="BDS_RAW_001",
            source_system="census",
            source_dataset="bds",
            source_resource_name="bds_state_year",
            check_name="Census BDS required variables returned",
            check_type="validity",
            severity="fail",
            passed=missing_variables == [],
            expected_value=list(required_variables),
            observed_value={"missing_variables": missing_variables},
            failed_message="Census BDS response is missing required variables.",
        ),
        _source_result(
            pipeline_run_id=pipeline_run_id,
            validation_check_id="BDS_RAW_002",
            source_system="census",
            source_dataset="bds",
            source_resource_name="bds_state_year",
            check_name="Census BDS state coverage",
            check_type="completeness",
            severity="fail",
            passed=state_count >= expected_state_count,
            expected_value=expected_state_count,
            observed_value=state_count,
            failed_message="Census BDS response does not include expected state coverage.",
        ),
    ]


def check_bls_laus_payload(
    payload: dict[str, Any],
    *,
    expected_series_ids: tuple[str, ...],
    pipeline_run_id: str,
) -> list[ValidationResult]:
    rows = payload.get("normalized_rows", [])
    observed_series_ids = {str(row.get("series_id")) for row in rows}
    missing_series_ids = sorted(set(expected_series_ids) - observed_series_ids)
    invalid_period_rows = [
        row
        for row in rows
        if not _is_month_start(str(row.get("observed_month", "")))
        or not str(row.get("period", "")).startswith("M")
    ]
    non_numeric_rows = [
        row
        for row in rows
        if not isinstance(row.get("value"), int | float)
    ]
    return [
        _source_result(
            pipeline_run_id=pipeline_run_id,
            validation_check_id="BLS_RAW_001",
            source_system="bls",
            source_dataset="laus",
            source_resource_name="laus_state_month",
            check_name="BLS expected series returned",
            check_type="completeness",
            severity="fail",
            passed=missing_series_ids == [],
            expected_value=list(expected_series_ids),
            observed_value={"missing_series_ids": missing_series_ids},
            failed_message="BLS LAUS response is missing expected series IDs.",
        ),
        _source_result(
            pipeline_run_id=pipeline_run_id,
            validation_check_id="BLS_RAW_002",
            source_system="bls",
            source_dataset="laus",
            source_resource_name="laus_state_month",
            check_name="BLS monthly periods valid",
            check_type="validity",
            severity="fail",
            passed=invalid_period_rows == [],
            expected_value="monthly M01-M12 rows with month-start dates",
            observed_value={"invalid_rows": len(invalid_period_rows)},
            failed_message="BLS LAUS response contains invalid monthly periods.",
        ),
        _source_result(
            pipeline_run_id=pipeline_run_id,
            validation_check_id="BLS_RAW_003",
            source_system="bls",
            source_dataset="laus",
            source_resource_name="laus_state_month",
            check_name="BLS values numeric",
            check_type="validity",
            severity="fail",
            passed=non_numeric_rows == [],
            expected_value="numeric values",
            observed_value={"non_numeric_rows": len(non_numeric_rows)},
            failed_message="BLS LAUS response contains non-numeric values.",
        ),
    ]


def _source_result(
    *,
    validation_check_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
    check_name: str,
    check_type: str,
    severity: str,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
    pipeline_run_id: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> ValidationResult:
    return make_validation_result(
        pipeline_run_id=pipeline_run_id or str((manifest or {}).get("pipeline_run_id", "unknown")),
        validation_check_id=validation_check_id,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name=check_name,
        check_type=check_type,
        severity=severity,
        passed=passed,
        expected_value=expected_value,
        observed_value=observed_value,
        passed_message=f"{check_name} check passed.",
        failed_message=failed_message,
    )


def _is_month_start(value: str) -> bool:
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed_date.day == 1
