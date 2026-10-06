from __future__ import annotations

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.run_models import LOCAL_FLOW_STAGES, failed_stage_for
from pipelines.validation.validation_failures import ValidationFailedError
from tests.unit.validation_flow_test_helpers import fixture_validation_inputs
from tests.unit.validation_test_helpers import read_json, rewrite_json


def test_failed_validation_can_write_summary_before_downstream_work(tmp_path):
    """Validate that failed validation can write summary before downstream work."""
    project_config, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="failed-run",
    )
    rewrite_json(
        extraction_paths.sba_7a_manifest_paths[0],
        local_raw_path=str(tmp_path / "missing.csv"),
    )

    completed_stages = [
        "initialize_run",
        "load_config",
        "extract_sources",
        "write_manifests",
    ]

    with pytest.raises(ValidationFailedError) as exc_info:
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="failed",
        completed_stages=completed_stages + ["write_run_summary"],
        failed_stage=failed_stage_for(completed_stages, LOCAL_FLOW_STAGES),
        error_message=str(exc_info.value),
        validation_result_path=context.run_validation_dir / "validation_results.json",
    )

    summary = read_json(summary_path)

    assert summary["status"] == "failed"
    assert summary["failed_stage"] == "validate_raw_outputs"
    assert "write_run_summary" in summary["completed_stages"]
    assert summary["validation_result_path"].endswith("validation_results.json")
