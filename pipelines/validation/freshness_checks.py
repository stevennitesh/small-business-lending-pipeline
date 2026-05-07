from __future__ import annotations

from datetime import date

from pipelines.validation.validation_result import ValidationResult, make_validation_result


def check_latest_observation_not_future(
    *,
    latest_observation_date: date,
    as_of_date: date,
    pipeline_run_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
) -> ValidationResult:
    return make_validation_result(
        pipeline_run_id=pipeline_run_id,
        validation_check_id="FRESHNESS_001",
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name="Latest observation is not future dated",
        check_type="freshness",
        severity="warning",
        passed=latest_observation_date <= as_of_date,
        expected_value=as_of_date.isoformat(),
        observed_value=latest_observation_date.isoformat(),
        passed_message="Latest observation is not future dated.",
        failed_message="Latest observation is future dated.",
    )
