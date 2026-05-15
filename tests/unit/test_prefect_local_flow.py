from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.validation.validation_result import ValidationFailedError


def test_local_flow_declares_expected_stage_order():
    assert local_flow.LOCAL_FLOW_STAGES == (
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
    assert local_flow.CLOUD_FLOW_STAGES == (
        "initialize_run",
        "load_config",
        "require_final_mode_config",
        "extract_sources",
        "write_manifests",
        "validate_raw_outputs",
        "upload_raw_artifacts_to_s3",
        "load_snowflake_raw_tables",
        "run_dbt_build",
        "collect_dbt_artifacts",
        "upload_dbt_artifacts_to_s3",
        "validate_bi_tables",
        "write_run_summary",
    )
    assert local_flow.FINAL_FLOW_STAGES == local_flow.CLOUD_FLOW_STAGES
    assert local_flow.CLOUD_FLOW_STAGES.index("validate_raw_outputs") < (
        local_flow.CLOUD_FLOW_STAGES.index("upload_raw_artifacts_to_s3")
    )
    assert local_flow.CLOUD_FLOW_STAGES.index("validate_raw_outputs") < (
        local_flow.CLOUD_FLOW_STAGES.index("load_snowflake_raw_tables")
    )
    assert local_flow.CLOUD_FLOW_STAGES.index("run_dbt_build") < (
        local_flow.CLOUD_FLOW_STAGES.index("validate_bi_tables")
    )


def test_final_mode_alias_normalizes_to_cloud_route(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="final",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="unit-test-bucket",
        pipeline_run_id="legacy-final-run",
    )

    assert context.run_mode == "cloud"
    assert context.stage_order == local_flow.CLOUD_FLOW_STAGES


def test_cloud_mode_requires_cloud_config_before_external_work(tmp_path, monkeypatch):
    for variable_name in (
        "S3_BUCKET",
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
    ):
        monkeypatch.delenv(variable_name, raising=False)
    monkeypatch.setattr(local_flow, "load_dotenv", lambda override=True: None)

    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="cloud-missing-config",
    )

    with pytest.raises(RuntimeError, match="Missing cloud mode configuration"):
        local_flow.require_final_mode_config.fn(context)


def test_cloud_summary_records_cloud_outputs(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
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
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["run_mode"] == "cloud"
    assert summary["route"] == "cloud"
    assert summary["dbt_target"] == "prod_snowflake"
    assert summary["s3_upload_summary"]["bucket"] == "unit-test-bucket"
    assert summary["snowflake_raw_load_summary"]["table_row_counts"] == {
        "RAW.RAW_SBA_7A_FOIA": 1
    }


def test_raw_artifact_store_matches_route(tmp_path):
    local_context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "local-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-route",
    )
    cloud_context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "cloud-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-route",
    )

    assert local_flow._raw_artifact_store(
        local_context,
        "local-live",
    ).storage_backend == "local"
    assert local_flow._raw_artifact_store(
        cloud_context,
        "cloud-bucket",
        s3_client=object(),
    ).storage_backend == "s3"


def test_fixture_extraction_and_validation_are_local_only(tmp_path):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="test-run",
    )

    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    validation_path = local_flow.validate_raw_outputs.fn(
        context,
        extraction_paths,
        project_config,
    )
    validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))

    assert validation_path.is_file()
    assert len(extraction_paths.manifest_paths) == 4
    assert all(Path(path).is_file() for path in extraction_paths.manifest_paths)
    assert {record["status"] for record in validation_payload} == {"passed"}
    assert "RAW_009" in {
        record["validation_check_id"]
        for record in validation_payload
    }


def test_fixture_manifests_use_source_config_identity(tmp_path):
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        "census_bds": replace(
            project_config.sources["census_bds"],
            source_system="custom_census",
            dataset_name="custom_bds",
        ),
        "bls_laus": replace(
            project_config.sources["bls_laus"],
            source_system="custom_bls",
            dataset_name="custom_laus",
        ),
    }
    project_config = replace(project_config, sources=sources)
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="fixture-identity-run",
    )

    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    census_manifest = json.loads(
        extraction_paths.census_bds_manifest_paths[0].read_text(encoding="utf-8")
    )
    bls_manifest = json.loads(
        extraction_paths.bls_laus_manifest_paths[0].read_text(encoding="utf-8")
    )

    assert census_manifest["source_system"] == "custom_census"
    assert census_manifest["dataset_name"] == "custom_bds"
    assert bls_manifest["source_system"] == "custom_bls"
    assert bls_manifest["dataset_name"] == "custom_laus"


def test_raw_validation_passes_source_config_identity_to_payload_checks(
    tmp_path,
    monkeypatch,
):
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        "sba_foia": replace(
            project_config.sources["sba_foia"],
            source_system="custom_sba",
            dataset_name="custom_sba_dataset",
        ),
        "census_bds": replace(
            project_config.sources["census_bds"],
            source_system="custom_census",
            dataset_name="custom_bds",
        ),
        "bls_laus": replace(
            project_config.sources["bls_laus"],
            source_system="custom_bls",
            dataset_name="custom_laus",
        ),
    }
    project_config = replace(project_config, sources=sources)
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="validation-identity-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    captured_identities = {}

    def fake_sba_check(manifests, *, required_resource_names, source_identity):
        captured_identities["sba_foia"] = source_identity
        return []

    def fake_census_check(
        payload,
        *,
        required_variables,
        expected_state_count,
        pipeline_run_id,
        source_identity,
    ):
        captured_identities["census_bds"] = source_identity
        return []

    def fake_bls_check(
        payload,
        *,
        expected_series_ids,
        pipeline_run_id,
        required_period_pattern,
        unemployment_rate_min,
        unemployment_rate_max,
        source_identity,
    ):
        captured_identities["bls_laus"] = source_identity
        return []

    monkeypatch.setattr(local_flow, "check_sba_required_resources", fake_sba_check)
    monkeypatch.setattr(local_flow, "check_census_bds_payload", fake_census_check)
    monkeypatch.setattr(local_flow, "check_bls_laus_payload", fake_bls_check)

    local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    assert captured_identities == {
        "sba_foia": project_config.source_identity("sba_foia"),
        "census_bds": project_config.source_identity("census_bds"),
        "bls_laus": project_config.source_identity("bls_laus"),
    }


def test_raw_validation_blocks_manifest_identity_mismatch(tmp_path):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="identity-mismatch-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    broken_manifest = extraction_paths.census_bds_manifest_paths[0]
    manifest_payload = json.loads(broken_manifest.read_text(encoding="utf-8"))
    manifest_payload["dataset_name"] = "wrong_dataset"
    broken_manifest.write_text(
        json.dumps(manifest_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationFailedError, match="RAW_010"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)


def test_raw_validation_blocks_missing_expected_manifest_resource(tmp_path):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="missing-manifest-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    extraction_paths = replace(
        extraction_paths,
        census_bds_manifest_paths=(),
        manifest_paths=tuple(
            path
            for path in extraction_paths.manifest_paths
            if path not in extraction_paths.census_bds_manifest_paths
        ),
    )

    with pytest.raises(ValidationFailedError, match="RAW_011"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)


def test_live_extraction_routes_to_source_extractors(tmp_path, monkeypatch):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="live",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="live-test-run",
        source_start_year=2020,
        source_end_year=2024,
    )
    calls = []

    def fake_sba_extract(**kwargs):
        calls.append(("sba", kwargs))
        return local_flow.SBAExtractionSummary(
            results={},
            manifest_paths={
                "sba_7a_fy2020_present": _write_manifest_stub(
                    tmp_path, "sba_7a_fy2020_present"
                ),
                "sba_504_fy2010_present": _write_manifest_stub(
                    tmp_path, "sba_504_fy2010_present"
                ),
            },
            warnings=[],
        )

    def fake_census_extract(**kwargs):
        calls.append(("census", kwargs))
        return local_flow.CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return local_flow.BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
        )

    monkeypatch.setattr(local_flow, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(local_flow, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(local_flow, "extract_bls_laus", fake_bls_extract)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)

    assert [name for name, _ in calls] == ["sba", "census", "bls"]
    assert calls[0][1]["config"] == project_config.sba
    assert calls[0][1]["source_identity"] == project_config.source_identity("sba_foia")
    assert calls[1][1]["config"] == project_config.census_bds
    assert calls[1][1]["source_identity"] == project_config.source_identity(
        "census_bds"
    )
    assert calls[1][1]["start_year"] == 2020
    assert calls[1][1]["end_year"] == 2024
    assert calls[2][1]["config"] == project_config.bls_laus
    assert calls[2][1]["source_identity"] == project_config.source_identity("bls_laus")
    assert calls[2][1]["start_year"] == 2019
    assert calls[2][1]["end_year"] == 2024
    assert len(extraction_paths.sba_7a_manifest_paths) == 1
    assert len(extraction_paths.sba_504_manifest_paths) == 1
    assert len(extraction_paths.manifest_paths) == 4


def test_live_bls_extraction_defaults_to_configured_history_start(tmp_path, monkeypatch):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="live",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="live-config-start-run",
        source_end_year=2024,
    )
    calls = []

    def fake_sba_extract(**kwargs):
        calls.append(("sba", kwargs))
        return local_flow.SBAExtractionSummary(
            results={},
            manifest_paths={
                "sba_7a_fy2020_present": _write_manifest_stub(
                    tmp_path, "sba_7a_fy2020_present"
                ),
                "sba_504_fy2010_present": _write_manifest_stub(
                    tmp_path, "sba_504_fy2010_present"
                ),
            },
            warnings=[],
        )

    def fake_census_extract(**kwargs):
        calls.append(("census", kwargs))
        return local_flow.CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return local_flow.BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
        )

    monkeypatch.setattr(local_flow, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(local_flow, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(local_flow, "extract_bls_laus", fake_bls_extract)

    local_flow.extract_sources.fn(context, project_config)

    bls_call = [kwargs for name, kwargs in calls if name == "bls"][0]
    assert project_config.bls_laus.start_year == 1990
    assert bls_call["start_year"] == 1989
    assert bls_call["end_year"] == 2024


def test_live_extraction_honors_disabled_sources(tmp_path, monkeypatch):
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        "census_bds": replace(project_config.sources["census_bds"], enabled=False),
    }
    project_config = replace(project_config, sources=sources)
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="live",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="live-disabled-source",
        source_start_year=2020,
        source_end_year=2024,
    )
    calls = []

    def fake_sba_extract(**kwargs):
        calls.append(("sba", kwargs))
        return local_flow.SBAExtractionSummary(
            results={},
            manifest_paths={
                "sba_7a_fy2020_present": _write_manifest_stub(
                    tmp_path, "sba_7a_fy2020_present"
                ),
                "sba_504_fy2010_present": _write_manifest_stub(
                    tmp_path, "sba_504_fy2010_present"
                ),
            },
            warnings=[],
        )

    def fake_census_extract(**kwargs):
        calls.append(("census", kwargs))
        return local_flow.CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return local_flow.BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
        )

    monkeypatch.setattr(local_flow, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(local_flow, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(local_flow, "extract_bls_laus", fake_bls_extract)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    expectations = local_flow._raw_validation_expectations(context, project_config)

    assert [name for name, _ in calls] == ["sba", "bls"]
    assert extraction_paths.census_bds_manifest_paths == ()
    assert len(extraction_paths.manifest_paths) == 3
    assert expectations.census_expected_state_count == 0


def test_validation_expectations_follow_extract_mode(tmp_path):
    project_config = local_flow.load_config.fn()
    fixture_context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "fixture-data"),
        duckdb_path=str(tmp_path / "fixture.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "fixture-profiles"),
        pipeline_run_id="fixture-run",
    )
    live_context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="live",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "live-data"),
        duckdb_path=str(tmp_path / "live.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "live-profiles"),
        pipeline_run_id="live-run",
    )

    fixture_expectations = local_flow._raw_validation_expectations(
        fixture_context,
        project_config,
    )
    live_expectations = local_flow._raw_validation_expectations(
        live_context,
        project_config,
    )

    assert fixture_expectations.census_expected_state_count == 2
    assert fixture_expectations.bls_expected_series_ids == (
        "LASST010000000000003",
        "LASST170000000000003",
    )
    assert live_expectations.census_expected_state_count == 51
    assert len(live_expectations.bls_expected_series_ids) == 51
    assert "sba_7a_fy2020_present" in live_expectations.sba_required_resource_names
    assert "sba_504_fy2010_present" in live_expectations.sba_required_resource_names


def test_failed_validation_can_write_summary_before_downstream_work(tmp_path):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="failed-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    broken_manifest = extraction_paths.sba_7a_manifest_paths[0]
    manifest_payload = json.loads(broken_manifest.read_text(encoding="utf-8"))
    manifest_payload["local_raw_path"] = str(tmp_path / "missing.csv")
    broken_manifest.write_text(
        json.dumps(manifest_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    completed_stages = ["initialize_run", "load_config", "extract_sources", "write_manifests"]

    with pytest.raises(ValidationFailedError) as exc_info:
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

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


def _write_manifest_stub(tmp_path: Path, resource_name: str) -> Path:
    path = tmp_path / f"{resource_name}.manifest.json"
    path.write_text(
        json.dumps(
            {
                "resource_name": resource_name,
                "local_raw_path": str(tmp_path / f"{resource_name}.raw"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path
