from __future__ import annotations

from pipelines.validation.validation_result import ValidationResult, make_validation_result


def check_row_count_captured(
    *,
    row_count: int | None,
    pipeline_run_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
) -> ValidationResult:
    return make_validation_result(
        pipeline_run_id=pipeline_run_id,
        validation_check_id="ROW_COUNT_001",
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name="Row count captured",
        check_type="completeness",
        severity="fail",
        passed=isinstance(row_count, int) and row_count >= 0,
        expected_value="non-negative integer row count",
        observed_value=row_count,
        passed_message="Row count is captured.",
        failed_message="Row count is missing or invalid.",
    )
