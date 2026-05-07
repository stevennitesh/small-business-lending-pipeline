from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipelines.utils.dates import utc_now_iso


VALID_SEVERITIES = frozenset({"fail", "warning", "info"})
VALID_STATUSES = frozenset({"passed", "warning", "failed"})


class ValidationFailedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    pipeline_run_id: str
    validation_check_id: str
    validation_scope: str
    source_system: str
    source_dataset: str
    source_resource_name: str
    check_name: str
    check_type: str
    severity: str
    status: str
    expected_value: Any
    observed_value: Any
    message: str
    checked_at_utc: str

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid validation severity: {self.severity}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid validation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_validation_result(
    *,
    pipeline_run_id: str,
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
    passed_message: str,
    failed_message: str,
    validation_scope: str = "raw",
) -> ValidationResult:
    status = "passed" if passed else ("warning" if severity == "warning" else "failed")
    return ValidationResult(
        pipeline_run_id=pipeline_run_id,
        validation_check_id=validation_check_id,
        validation_scope=validation_scope,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name=check_name,
        check_type=check_type,
        severity=severity,
        status=status,
        expected_value=expected_value,
        observed_value=observed_value,
        message=passed_message if passed else failed_message,
        checked_at_utc=utc_now_iso(),
    )


def write_validation_results(
    results: list[ValidationResult],
    path: Path | str,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def assert_no_blocking_failures(results: list[ValidationResult]) -> None:
    failures = [
        result
        for result in results
        if result.severity == "fail" and result.status == "failed"
    ]
    if failures:
        failed_ids = ", ".join(result.validation_check_id for result in failures)
        raise ValidationFailedError(
            f"Critical raw validation failures block loading: {failed_ids}"
        )
