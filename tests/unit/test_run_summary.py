from __future__ import annotations

import json
from pathlib import Path

from pipelines.flows import run_summary
import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.run_models import LocalRunContext
from pipelines.powerbi.export_schema import BI_EXPORT_TABLES, EXTRA_SBA_KPI_BI_TABLES
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.validation.raw_validation_models import RawValidationOutput


def test_flow_summary_can_record_expanded_powerbi_contract(tmp_path):
    context = _run_summary_context(
        tmp_path,
        pipeline_run_id="expanded-powerbi-contract",
    )
    bi_row_counts = {table_name: 1 for table_name in BI_EXPORT_TABLES}
    export_paths = [
        str(context.run_export_dir / f"{table_name}.csv")
        for table_name in BI_EXPORT_TABLES
    ]

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="success",
        completed_stages=["validate_bi_tables", "export_bi_tables"],
        bi_row_counts=bi_row_counts,
        export_paths=export_paths,
    )
    summary = _read_summary(summary_path)

    assert set(EXTRA_SBA_KPI_BI_TABLES) <= set(summary["bi_row_counts"])
    assert {
        f"{table_name}.csv"
        for table_name in EXTRA_SBA_KPI_BI_TABLES
    } <= {Path(path).name for path in summary["export_paths"]}


def test_flow_summary_records_stage_durations(tmp_path):
    context = _run_summary_context(
        tmp_path,
        pipeline_run_id="local-stage-durations",
    )

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="success",
        completed_stages=["extract_sources", "write_run_summary"],
        stage_durations_seconds={"extract_sources": 1.25},
    )
    summary = _read_summary(summary_path)

    assert summary["stage_durations_seconds"]["extract_sources"] == 1.25
    assert summary["stage_durations_seconds"]["write_run_summary"] >= 0
    assert summary["status"] == "success"


def test_run_summary_helper_records_stage_durations_once(tmp_path):
    context = _run_summary_context(
        tmp_path,
        pipeline_run_id="run-summary-helper",
    )

    summary_path = run_summary.write_run_summary_for_context(
        context,
        status="success",
        completed_stages=["initialize_run", "write_run_summary"],
        stage_durations_seconds={"initialize_run": 0.5},
    )
    summary = _read_summary(summary_path)

    assert summary["stage_durations_seconds"]["initialize_run"] == 0.5
    assert summary["stage_durations_seconds"]["write_run_summary"] >= 0
    assert summary["status"] == "success"


def test_cloud_summary_records_cloud_outputs(tmp_path):
    context = _run_summary_context(
        tmp_path,
        run_mode="cloud",
        dbt_target="prod_snowflake",
        s3_bucket="unit-test-bucket",
        pipeline_run_id="cloud-run",
    )

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="success",
        completed_stages=["initialize_run", "write_run_summary"],
        s3_upload_summary={
            "bucket": "unit-test-bucket",
            "uploaded_objects": ["s3://unit-test-bucket/raw/example.csv"],
        },
        snowflake_raw_load_summary={
            "database": "SMALL_BUSINESS_LENDING",
            "raw_schema": "RAW",
            "table_row_counts": {"RAW.RAW_SBA_7A_FOIA": 1},
        },
        manifest_artifact_uris=[
            "s3://unit-test-bucket/manifests/sba/manifest.json"
        ],
    )
    summary = _read_summary(summary_path)

    assert summary["run_mode"] == "cloud"
    assert summary["route"] == "cloud"
    assert summary["dbt_target"] == "prod_snowflake"
    assert summary["s3_upload_summary"]["bucket"] == "unit-test-bucket"
    assert summary["manifest_artifact_uris"] == [
        "s3://unit-test-bucket/manifests/sba/manifest.json"
    ]
    assert summary["snowflake_raw_load_summary"]["table_row_counts"] == {
        "RAW.RAW_SBA_7A_FOIA": 1
    }


def test_run_summary_records_validation_output_path_and_uri(tmp_path):
    context = _run_summary_context(
        tmp_path,
        run_mode="cloud",
        dbt_target="prod_snowflake",
        s3_bucket="unit-test-bucket",
        pipeline_run_id="validation-output-summary",
    )
    validation_output = RawValidationOutput(
        local_path=context.run_validation_dir / "validation_results.json",
        artifact_location=ArtifactLocation(
            storage_backend="s3",
            artifact_uri="s3://unit-test-bucket/validation/results.json",
            artifact_key="validation/results.json",
            local_path=None,
            s3_uri="s3://unit-test-bucket/validation/results.json",
        ),
    )

    summary_path = run_summary.write_run_summary_for_context(
        context,
        status="success",
        completed_stages=["validate_raw_outputs"],
        validation_result_path=validation_output,
    )
    summary = _read_summary(summary_path)

    assert summary["validation_result_path"].endswith("validation_results.json")
    assert (
        summary["validation_result_uri"]
        == "s3://unit-test-bucket/validation/results.json"
    )


def _run_summary_context(
    tmp_path: Path,
    *,
    pipeline_run_id: str,
    run_mode: str = "local",
    dbt_target: str = "dev_duckdb",
    s3_bucket: str | None = None,
) -> LocalRunContext:
    return local_flow.initialize_run.fn(
        run_mode=run_mode,
        extract_mode="fixture",
        dbt_target=dbt_target,
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
    )


def _read_summary(summary_path: Path) -> dict:
    return json.loads(summary_path.read_text(encoding="utf-8"))
