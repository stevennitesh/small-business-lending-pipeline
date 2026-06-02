"""Pipeline-health validation helpers for flow-level health reporting.

These helpers are not wired into the raw validation runner yet. Raw validation
currently focuses on extract artifacts, manifests, and source payload shape;
row-count drift and freshness status belong to the later pipeline-health layer.
"""

from __future__ import annotations

from datetime import date

from pipelines.validation.raw_validation_check_catalog import (
    ValidationCheckDefinition,
)
from pipelines.validation.validation_result import (
    ValidationResult,
    make_check_validation_result,
)


PIPELINE_ROW_COUNT_CAPTURED = ValidationCheckDefinition(
    validation_check_id="ROW_COUNT_001",
    check_name="Row count captured",
    check_type="completeness",
    severity="fail",
)
PIPELINE_LATEST_OBSERVATION_NOT_FUTURE = ValidationCheckDefinition(
    validation_check_id="FRESHNESS_001",
    check_name="Latest observation is not future dated",
    check_type="freshness",
    severity="warning",
)


def check_row_count_captured(
    *,
    row_count: int | None,
    pipeline_run_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
) -> ValidationResult:
    """Create a pipeline-health result for row-count presence."""
    return make_check_validation_result(
        pipeline_run_id=pipeline_run_id,
        check_definition=PIPELINE_ROW_COUNT_CAPTURED,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        passed=isinstance(row_count, int) and row_count >= 0,
        expected_value="non-negative integer row count",
        observed_value=row_count,
        failed_message="Row count is missing or invalid.",
    )


def check_latest_observation_not_future(
    *,
    latest_observation_date: date,
    as_of_date: date,
    pipeline_run_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
) -> ValidationResult:
    """Create a pipeline-health result for freshness date sanity."""
    return make_check_validation_result(
        pipeline_run_id=pipeline_run_id,
        check_definition=PIPELINE_LATEST_OBSERVATION_NOT_FUTURE,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        passed=latest_observation_date <= as_of_date,
        expected_value=as_of_date.isoformat(),
        observed_value=latest_observation_date.isoformat(),
        failed_message="Latest observation is future dated.",
    )
