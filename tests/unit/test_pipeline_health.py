from __future__ import annotations

from datetime import date

from pipelines.flows.pipeline_health import (
    check_latest_observation_not_future,
    check_row_count_captured,
)


def test_pipeline_health_helpers_support_warnings():
    """Validate that pipeline health helpers support warnings."""
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
