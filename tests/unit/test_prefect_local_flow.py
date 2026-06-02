from __future__ import annotations

import sys

import pytest

import pipelines.cli.run_lending_pipeline as run_lending_pipeline_cli
from pipelines.flows.run_models import (
    CLOUD_FLOW_STAGES,
    LOCAL_FLOW_STAGES,
    FlowRunState,
)
from pipelines.flows.stage_execution import run_timed_flow_stage, run_timed_stage


def test_local_flow_declares_expected_stage_order():
    assert LOCAL_FLOW_STAGES == (
        "initialize_run",
        "load_config",
        "extract_sources",
        "write_manifests",
        "validate_raw_outputs",
        "load_duckdb_raw_tables",
        "run_dbt_build",
        "collect_dbt_artifacts",
        "validate_bi_tables",
        "export_bi_tables",
        "write_run_summary",
    )


def test_cloud_flow_declares_expected_stage_order():
    assert CLOUD_FLOW_STAGES == (
        "initialize_run",
        "load_config",
        "require_cloud_mode_config",
        "extract_sources",
        "write_manifests",
        "validate_raw_outputs",
        "record_raw_artifact_locations",
        "load_snowflake_raw_tables",
        "run_dbt_build",
        "collect_dbt_artifacts",
        "upload_dbt_artifacts_to_s3",
        "validate_bi_tables",
        "write_run_summary",
    )
    assert CLOUD_FLOW_STAGES.index("validate_raw_outputs") < (
        CLOUD_FLOW_STAGES.index("record_raw_artifact_locations")
    )
    assert CLOUD_FLOW_STAGES.index("validate_raw_outputs") < (
        CLOUD_FLOW_STAGES.index("load_snowflake_raw_tables")
    )
    assert CLOUD_FLOW_STAGES.index("run_dbt_build") < (
        CLOUD_FLOW_STAGES.index("validate_bi_tables")
    )


def test_timed_stage_records_duration_when_stage_fails():
    stage_durations: dict[str, float] = {}

    def fail_stage():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_timed_stage(stage_durations, "validate_raw_outputs", fail_stage)

    assert "validate_raw_outputs" in stage_durations
    assert stage_durations["validate_raw_outputs"] >= 0


def test_timed_flow_stage_records_duration_and_completion():
    state = FlowRunState()

    result = run_timed_flow_stage(
        state,
        "extract_sources",
        lambda: "ok",
        completed_stages=("extract_sources", "write_manifests"),
    )

    assert result == "ok"
    assert state.completed_stages == ["extract_sources", "write_manifests"]
    assert "extract_sources" in state.stage_durations_seconds


def test_flow_run_state_tracks_failed_stage():
    state = FlowRunState()
    state.complete("initialize_run")
    state.complete("load_config")

    assert state.completed_with_summary() == [
        "initialize_run",
        "load_config",
        "write_run_summary",
    ]
    assert state.failed_stage(LOCAL_FLOW_STAGES) == "extract_sources"


def test_lending_pipeline_cli_delegates_to_flow(monkeypatch, capsys):
    calls = {}

    def fake_lending_pipeline_flow(**kwargs):
        calls.update(kwargs)
        return "data/validation/pipeline_run_id=cli/run_summary.json"

    monkeypatch.setattr(
        run_lending_pipeline_cli,
        "lending_pipeline_flow",
        fake_lending_pipeline_flow,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_lending_pipeline",
            "--run-mode",
            "cloud",
            "--extract-mode",
            "live",
            "--dbt-target",
            "prod_snowflake",
            "--source-start-year",
            "2020",
            "--source-end-year",
            "2024",
        ],
    )

    run_lending_pipeline_cli.main()

    assert calls["run_mode"] == "cloud"
    assert calls["extract_mode"] == "live"
    assert calls["dbt_target"] == "prod_snowflake"
    assert calls["source_start_year"] == 2020
    assert calls["source_end_year"] == 2024
    assert capsys.readouterr().out == (
        "data/validation/pipeline_run_id=cli/run_summary.json\n"
    )
