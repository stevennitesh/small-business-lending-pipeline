from __future__ import annotations

import json
from pathlib import Path

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.validation.validation_result import ValidationFailedError


def test_local_flow_declares_expected_stage_order():
    assert local_flow.FLOW_STAGES == (
        "initialize_run",
        "load_config",
        "extract_sources",
        "validate_raw_outputs",
        "write_manifests",
        "load_duckdb_raw_tables",
        "run_dbt_build",
        "collect_dbt_artifacts",
        "validate_bi_tables",
        "export_bi_tables",
        "write_run_summary",
    )


def test_fixture_extraction_and_validation_are_local_only(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        pipeline_run_id="test-run",
    )

    extraction_paths = local_flow.extract_sources.fn(context)
    validation_path = local_flow.validate_raw_outputs.fn(context, extraction_paths)
    validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))

    assert validation_path.is_file()
    assert len(extraction_paths.manifest_paths) == 4
    assert all(Path(path).is_file() for path in extraction_paths.manifest_paths)
    assert {record["status"] for record in validation_payload} == {"passed"}


def test_failed_validation_can_write_summary_before_downstream_work(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        pipeline_run_id="failed-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context)
    broken_manifest = extraction_paths.sba_7a_manifest_paths[0]
    manifest_payload = json.loads(broken_manifest.read_text(encoding="utf-8"))
    manifest_payload["local_raw_path"] = str(tmp_path / "missing.csv")
    broken_manifest.write_text(
        json.dumps(manifest_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    completed_stages = ["initialize_run", "load_config", "extract_sources", "write_manifests"]

    with pytest.raises(ValidationFailedError) as exc_info:
        local_flow.validate_raw_outputs.fn(context, extraction_paths)

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="failed",
        completed_stages=completed_stages + ["write_run_summary"],
        failed_stage=local_flow._failed_stage(completed_stages),
        error_message=str(exc_info.value),
        validation_result_path=context.run_validation_dir / "validation_results.json",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["status"] == "failed"
    assert summary["failed_stage"] == "validate_raw_outputs"
    assert "write_run_summary" in summary["completed_stages"]
    assert summary["validation_result_path"].endswith("validation_results.json")
