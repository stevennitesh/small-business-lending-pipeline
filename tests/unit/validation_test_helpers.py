from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pipelines.validation.raw_validation_check_catalog import RAW_FILE_EXISTS
from pipelines.validation.raw_validation_resources import CENSUS_BDS_RESOURCE_NAME
from pipelines.validation.validation_result import (
    ValidationResult,
    make_validation_result,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_bytes(payload: bytes) -> Any:
    return json.loads(payload)


def rewrite_json(path: Path, **updates) -> None:
    payload = read_json(path)
    payload.update(updates)
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def raw_file_exists_result(
    *,
    pipeline_run_id: str = "run-123",
    source_system: str = "census",
    source_dataset: str = "bds",
    source_resource_name: str = CENSUS_BDS_RESOURCE_NAME,
    passed: bool = True,
    observed_value: Any = "file exists",
) -> ValidationResult:
    return make_validation_result(
        pipeline_run_id=pipeline_run_id,
        validation_check_id=RAW_FILE_EXISTS.validation_check_id,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name=RAW_FILE_EXISTS.check_name,
        check_type=RAW_FILE_EXISTS.check_type,
        severity=RAW_FILE_EXISTS.severity,
        passed=passed,
        expected_value="file exists",
        observed_value=observed_value,
        failed_message="Raw file is missing.",
    )


def raw_check_result(
    results: list[ValidationResult],
    validation_check_id: str,
) -> ValidationResult:
    return next(
        result
        for result in results
        if result.validation_check_id == validation_check_id
    )


def validation_check_ids(
    results: Iterable[ValidationResult | dict[str, Any]],
) -> list[str]:
    return [_validation_check_id(result) for result in results]


def validation_check_id_set(
    results: Iterable[ValidationResult | dict[str, Any]],
) -> set[str]:
    return set(validation_check_ids(results))


def assert_validation_output_contains(path: Path, *expected_check_ids: str) -> None:
    observed_ids = validation_check_id_set(read_json(path))
    assert set(expected_check_ids) <= observed_ids


def failed_check_ids(results: Iterable[ValidationResult | dict[str, Any]]) -> set[str]:
    return {
        _validation_check_id(result)
        for result in results
        if _validation_status(result) == "failed"
    }


def _validation_check_id(result: ValidationResult | dict[str, Any]) -> str:
    if isinstance(result, ValidationResult):
        return result.validation_check_id
    return str(result["validation_check_id"])


def _validation_status(result: ValidationResult | dict[str, Any]) -> str:
    if isinstance(result, ValidationResult):
        return result.status
    return str(result["status"])
