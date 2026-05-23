from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.storage.raw_artifacts import RawArtifactReader, S3RawArtifactStore
from pipelines.validation.validation_result import ValidationFailedError
from scripts.export_powerbi_tables import BI_EXPORT_TABLES


EXTRA_SBA_KPI_BI_TABLES = {
    "bi_lending_performance",
    "bi_lending_status_mix",
    "bi_lending_terms_pricing",
    "bi_lending_jobs_impact",
}


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
    assert local_flow.CLOUD_FLOW_STAGES.index("validate_raw_outputs") < (
        local_flow.CLOUD_FLOW_STAGES.index("record_raw_artifact_locations")
    )
    assert local_flow.CLOUD_FLOW_STAGES.index("validate_raw_outputs") < (
        local_flow.CLOUD_FLOW_STAGES.index("load_snowflake_raw_tables")
    )
    assert local_flow.CLOUD_FLOW_STAGES.index("run_dbt_build") < (
        local_flow.CLOUD_FLOW_STAGES.index("validate_bi_tables")
    )


def test_flow_uses_shared_powerbi_export_contract(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-powerbi-contract",
    )

    assert local_flow.BI_TABLES == BI_EXPORT_TABLES
    assert EXTRA_SBA_KPI_BI_TABLES <= set(local_flow.BI_TABLES)
    assert context.run_export_dir == tmp_path / "data" / "exports" / "powerbi"


def test_flow_summary_can_record_expanded_powerbi_contract(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="expanded-powerbi-contract",
    )
    bi_row_counts = {table_name: 1 for table_name in local_flow.BI_TABLES}
    export_paths = [
        str(context.run_export_dir / f"{table_name}.csv")
        for table_name in local_flow.BI_TABLES
    ]

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="success",
        completed_stages=["validate_bi_tables", "export_bi_tables"],
        bi_row_counts=bi_row_counts,
        export_paths=export_paths,
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert EXTRA_SBA_KPI_BI_TABLES <= set(summary["bi_row_counts"])
    assert {
        f"{table_name}.csv"
        for table_name in EXTRA_SBA_KPI_BI_TABLES
    } <= {Path(path).name for path in summary["export_paths"]}


def test_flow_summary_records_stage_durations(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-stage-durations",
    )

    summary_path = local_flow.write_run_summary.fn(
        context,
        status="success",
        completed_stages=["extract_sources", "write_run_summary"],
        stage_durations_seconds={"extract_sources": 1.25},
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["stage_durations_seconds"]["extract_sources"] == 1.25
    assert summary["stage_durations_seconds"]["write_run_summary"] >= 0
    assert summary["status"] == "success"


def test_timed_stage_records_duration_when_stage_fails():
    stage_durations: dict[str, float] = {}

    def fail_stage():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        local_flow._run_timed_stage(stage_durations, "validate_raw_outputs", fail_stage)

    assert "validate_raw_outputs" in stage_durations
    assert stage_durations["validate_raw_outputs"] >= 0


def test_flow_powerbi_export_dir_can_use_env_override(tmp_path, monkeypatch):
    export_dir = tmp_path / "custom-powerbi"
    monkeypatch.setenv("POWERBI_EXPORT_DIR", str(export_dir))

    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-powerbi-env-override",
    )

    assert context.run_export_dir == export_dir
    assert export_dir.is_dir()


def test_flow_powerbi_export_dir_argument_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("POWERBI_EXPORT_DIR", str(tmp_path / "env-powerbi"))
    export_dir = tmp_path / "arg-powerbi"

    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        powerbi_export_dir=str(export_dir),
        s3_bucket=None,
        pipeline_run_id="local-powerbi-arg-override",
    )

    assert context.run_export_dir == export_dir
    assert export_dir.is_dir()


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
        monkeypatch.setenv(variable_name, "")
    monkeypatch.setenv("SNOWFLAKE_STORAGE_INTEGRATION", "")
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
        local_flow.require_cloud_mode_config.fn(context)


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
        manifest_artifact_uris=[
            "s3://unit-test-bucket/manifests/sba/manifest.json"
        ],
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

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


def test_snowflake_bi_schema_can_use_cloud_smoke_prefix(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_BI_SCHEMA", raising=False)
    monkeypatch.setenv("DBT_SCHEMA_PREFIX", "SMOKE")

    assert local_flow._snowflake_bi_schema() == "SMOKE_BI"

    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "CUSTOM_BI")

    assert local_flow._snowflake_bi_schema() == "CUSTOM_BI"


def test_cloud_bi_validation_uses_expanded_contract_without_live_credentials(monkeypatch):
    executed_sql: list[str] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, sql):
            executed_sql.append(sql)

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "SMOKE_BI")
    monkeypatch.setattr(local_flow.SnowflakeConfig, "from_env", lambda: object())
    monkeypatch.setattr(local_flow, "connect_to_snowflake", lambda config: FakeConnection())
    monkeypatch.setattr(local_flow, "load_dotenv", lambda override=True: None)

    row_counts = local_flow._validate_snowflake_bi_tables()

    assert row_counts == {table_name: 1 for table_name in local_flow.BI_TABLES}
    for table_name in EXTRA_SBA_KPI_BI_TABLES:
        assert f"SMOKE_BI.{table_name.upper()}" in "\n".join(executed_sql)


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
    assert local_flow._artifact_store(
        local_context,
        "local-live",
    ).storage_backend == "local"
    assert local_flow._artifact_store(
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
    validation_output = local_flow.validate_raw_outputs.fn(
        context,
        extraction_paths,
        project_config,
    )
    validation_payload = json.loads(
        validation_output.local_path.read_text(encoding="utf-8")
    )

    assert validation_output.local_path.is_file()
    assert validation_output.artifact_location is None
    assert len(extraction_paths.manifest_paths) == 4
    assert all(Path(path).is_file() for path in extraction_paths.manifest_paths)
    assert {record["status"] for record in validation_payload} == {"passed"}
    assert "RAW_009" in {
        record["validation_check_id"]
        for record in validation_payload
    }
    bls_manifest = json.loads(
        extraction_paths.bls_laus_manifest_paths[0].read_text(encoding="utf-8")
    )
    bls_payload = json.loads(
        Path(bls_manifest["local_raw_path"]).read_text(encoding="utf-8")
    )
    assert bls_manifest["row_count"] == 4
    assert {
        str(row["year"])
        for row in bls_payload["normalized_rows"]
    } == {"2025", "2026"}


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

    def fake_sba_check(
        manifests,
        *,
        required_resource_names,
        source_identity,
        artifact_reader,
        readable_resource_names,
    ):
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


def test_raw_validation_writes_results_for_missing_manifest_reference(tmp_path):
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
        pipeline_run_id="missing-manifest-reference-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    missing_manifest = extraction_paths.census_bds_manifest_paths[0]
    missing_manifest.unlink()

    with pytest.raises(ValidationFailedError, match="RAW_004"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    validation_payload = json.loads(
        (context.run_validation_dir / "validation_results.json").read_text(
            encoding="utf-8"
        )
    )
    failed_ids = {
        record["validation_check_id"]
        for record in validation_payload
        if record["status"] == "failed"
    }

    assert "RAW_004" in failed_ids
    assert "RAW_009" in {
        record["validation_check_id"]
        for record in validation_payload
    }


def test_raw_validation_writes_results_for_malformed_manifest_json(tmp_path):
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
        pipeline_run_id="malformed-manifest-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    malformed_manifest = extraction_paths.census_bds_manifest_paths[0]
    malformed_manifest.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValidationFailedError, match="RAW_014"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    validation_payload = json.loads(
        (context.run_validation_dir / "validation_results.json").read_text(
            encoding="utf-8"
        )
    )
    failed_ids = {
        record["validation_check_id"]
        for record in validation_payload
        if record["status"] == "failed"
    }

    assert "RAW_014" in failed_ids
    assert "RAW_009" in {
        record["validation_check_id"]
        for record in validation_payload
    }


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


def test_cloud_live_extraction_passes_s3_manifest_artifact_store(
    tmp_path,
    monkeypatch,
):
    project_config = local_flow.load_config.fn()
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="live",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-live-test-run",
        source_start_year=2020,
        source_end_year=2024,
    )
    calls = []

    def fake_manifest_location(resource_name: str):
        return local_flow.ArtifactLocation(
            storage_backend="s3",
            artifact_uri=f"s3://cloud-bucket/manifests/test/{resource_name}.json",
            artifact_key=f"manifests/test/{resource_name}.json",
            local_path=None,
            s3_uri=f"s3://cloud-bucket/manifests/test/{resource_name}.json",
        )

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
            manifest_locations={
                "sba_7a_fy2020_present": fake_manifest_location(
                    "sba_7a_fy2020_present"
                ),
                "sba_504_fy2010_present": fake_manifest_location(
                    "sba_504_fy2010_present"
                ),
            },
        )

    def fake_census_extract(**kwargs):
        calls.append(("census", kwargs))
        return local_flow.CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
            manifest_location=fake_manifest_location("bds_state_year"),
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return local_flow.BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
            manifest_location=fake_manifest_location("laus_state_month"),
        )

    monkeypatch.setattr(local_flow, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(local_flow, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(local_flow, "extract_bls_laus", fake_bls_extract)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)

    assert [
        kwargs["manifest_artifact_store"].storage_backend
        for _, kwargs in calls
    ] == ["s3", "s3", "s3"]
    assert len(extraction_paths.manifest_locations) == 4
    assert {
        location.storage_backend for location in extraction_paths.manifest_locations
    } == {"s3"}


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


def test_local_flow_generated_dbt_profile_uses_single_duckdb_thread(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        pipeline_run_id="profile-thread-check",
    )

    local_flow._ensure_dbt_profile(context)

    profile_text = (tmp_path / "profiles" / "profiles.yml").read_text(
        encoding="utf-8"
    )
    assert "threads: 1" in profile_text


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


def test_cloud_fixture_extraction_and_validation_use_s3_backed_manifests(
    tmp_path,
    monkeypatch,
):
    project_config = local_flow.load_config.fn()
    s3_client = FakeS3ObjectClient()
    monkeypatch.setattr(
        local_flow,
        "_raw_artifact_store",
        lambda context, bucket, s3_client=None: S3RawArtifactStore(
            bucket=bucket,
            s3_client=s3_client or FakeS3ObjectClientHolder.client,
        )
        if context.is_cloud_route
        else local_flow.LocalRawArtifactStore(
            data_root=context.data_root,
            s3_bucket=bucket,
        ),
    )
    FakeS3ObjectClientHolder.client = s3_client
    monkeypatch.setattr(
        local_flow,
        "_artifact_store",
        lambda context, bucket, s3_client=None: local_flow.S3ArtifactStore(
            bucket=bucket,
            s3_client=s3_client or FakeS3ObjectClientHolder.client,
        )
        if context.is_cloud_route
        else local_flow.LocalArtifactStore(
            data_root=context.data_root,
            s3_bucket=bucket,
        ),
    )
    monkeypatch.setattr(
        local_flow,
        "_artifact_reader",
        lambda context, s3_client=None: local_flow.ArtifactReader(
            s3_client=FakeS3ObjectClientHolder.client
            if context.is_cloud_route
            else s3_client
        ),
    )
    monkeypatch.setattr(
        local_flow,
        "_raw_artifact_reader",
        lambda context, s3_client=None: RawArtifactReader(
            s3_client=FakeS3ObjectClientHolder.client
            if context.is_cloud_route
            else s3_client
        ),
    )
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="unit-test-bucket",
        pipeline_run_id="cloud-fixture-run",
    )
    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    validation_output = local_flow.validate_raw_outputs.fn(
        context,
        extraction_paths,
        project_config,
    )
    validation_results = json.loads(
        validation_output.local_path.read_text(encoding="utf-8")
    )
    manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in extraction_paths.manifest_paths
    ]

    assert {manifest["storage_backend"] for manifest in manifests} == {"s3"}
    assert all(manifest["local_raw_path"] is None for manifest in manifests)
    assert all(manifest["raw_uri"].startswith("s3://unit-test-bucket/") for manifest in manifests)
    assert {result["status"] for result in validation_results} == {"passed"}
    assert validation_output.artifact_location is not None
    assert validation_output.artifact_location.artifact_uri.startswith(
        "s3://unit-test-bucket/validation/pipeline/raw_validation/"
    )
    validation_key = validation_output.artifact_location.artifact_key
    assert json.loads(s3_client.objects[("unit-test-bucket", validation_key)]) == (
        validation_results
    )


class FakeS3ObjectClientHolder:
    client: "FakeS3ObjectClient"


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3ObjectClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}


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
