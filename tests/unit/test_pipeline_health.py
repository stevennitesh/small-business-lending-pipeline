from __future__ import annotations

from datetime import date

from pipelines.flows.pipeline_health import (
    check_latest_observation_not_future,
    check_row_count_captured,
)
from pipelines.validation import pipeline_health as validation_pipeline_health


def test_pipeline_health_helpers_support_warnings():
    row_count_result = check_row_count_captured(
        row_count=10,
        pipeline_run_id="run-123",
        source_system="bls",
        source_dataset="laus",
        source_resource_name="laus_state_month",
    )
    future_result = check_latest_observation_not_future(
        latest_observation_date=date(2026, 6, 1),
        as_of_date=date(2026, 5, 7),
        pipeline_run_id="run-123",
        source_system="bls",
        source_dataset="laus",
        source_resource_name="laus_state_month",
    )

    assert row_count_result.status == "passed"
    assert future_result.severity == "warning"
    assert future_result.status == "warning"


def test_validation_pipeline_health_imports_remain_compatible():
    assert (
        validation_pipeline_health.check_row_count_captured
        is check_row_count_captured
    )
    assert (
        validation_pipeline_health.check_latest_observation_not_future
        is check_latest_observation_not_future
    )
