from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import pipelines.cli.run_lending_pipeline as run_lending_pipeline_cli
from pipelines.extract.bls_laus_extract import BLSLAUSExtractionSummary
from pipelines.extract.census_bds_extract import CensusBDSExtractionSummary
from pipelines.extract.sba_extract import SBAExtractionSummary
from pipelines.flows import dbt_bi, raw_loads, source_extracts
import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.extraction_artifact_stores import resolve_extraction_bucket
from pipelines.flows.extraction_manifests import (
    ExtractionPaths,
    extraction_paths_from_manifest_maps,
)
from pipelines.flows.run_models import (
    FlowRunState,
)
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    artifact_store_for_route,
    raw_artifact_store_for_route,
)
from pipelines.validation.raw_validation_models import RawValidationOutput
from pipelines.validation.raw_validation_expectations import raw_validation_expectations
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
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


def test_timed_stage_records_duration_when_stage_fails():
    stage_durations: dict[str, float] = {}

    def fail_stage():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        local_flow._run_timed_stage(stage_durations, "validate_raw_outputs", fail_stage)

    assert "validate_raw_outputs" in stage_durations
    assert stage_durations["validate_raw_outputs"] >= 0


def test_flow_run_state_tracks_failed_stage():
    state = FlowRunState()
    state.complete("initialize_run")
    state.complete("load_config")

    assert state.completed_with_summary() == [
        "initialize_run",
        "load_config",
        "write_run_summary",
    ]
    assert state.failed_stage(local_flow.LOCAL_FLOW_STAGES) == "extract_sources"


def test_snowflake_bi_schema_can_use_cloud_smoke_prefix(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_BI_SCHEMA", raising=False)
    monkeypatch.setenv("DBT_SCHEMA_PREFIX", "SMOKE")

    assert dbt_bi.snowflake_bi_schema() == "SMOKE_BI"

    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "CUSTOM_BI")

    assert dbt_bi.snowflake_bi_schema() == "CUSTOM_BI"


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
    monkeypatch.setattr(dbt_bi.SnowflakeConfig, "from_env", lambda: object())
    monkeypatch.setattr(dbt_bi, "connect_to_snowflake", lambda config: FakeConnection())
    monkeypatch.setattr(dbt_bi, "load_dotenv", lambda override=True: None)

    row_counts = dbt_bi.validate_snowflake_bi_tables()

    assert row_counts == {table_name: 1 for table_name in local_flow.BI_TABLES}
    for table_name in EXTRA_SBA_KPI_BI_TABLES:
        assert f'"SMOKE_BI"."{table_name.upper()}"' in "\n".join(executed_sql)


def test_cloud_bi_validation_rejects_invalid_schema_identifier(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "SMOKE_BI;drop table BI")
    monkeypatch.setattr(dbt_bi.SnowflakeConfig, "from_env", lambda: object())
    monkeypatch.setattr(dbt_bi, "load_dotenv", lambda override=True: None)

    with pytest.raises(ValueError, match="Invalid Snowflake identifier"):
        dbt_bi.validate_snowflake_bi_tables()


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

    assert raw_artifact_store_for_route(
        cloud_route=local_context.is_cloud_route,
        data_root=local_context.data_root,
        bucket="local-live",
    ).storage_backend == "local"
    assert raw_artifact_store_for_route(
        cloud_route=cloud_context.is_cloud_route,
        data_root=cloud_context.data_root,
        bucket="cloud-bucket",
        s3_client=object(),
    ).storage_backend == "s3"
    assert artifact_store_for_route(
        cloud_route=local_context.is_cloud_route,
        data_root=local_context.data_root,
        bucket="local-live",
    ).storage_backend == "local"
    assert artifact_store_for_route(
        cloud_route=cloud_context.is_cloud_route,
        data_root=cloud_context.data_root,
        bucket="cloud-bucket",
        s3_client=object(),
    ).storage_backend == "s3"


def test_extraction_bucket_rejects_missing_cloud_bucket(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "cloud-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="cloud-missing-bucket",
    )

    with pytest.raises(RuntimeError, match="configured S3 bucket"):
        resolve_extraction_bucket(
            context,
            default_bucket="local-live",
            s3_bucket_resolver=lambda _: None,
        )


def test_extraction_bucket_uses_default_only_for_local_route(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "local-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-default-bucket",
    )

    assert (
        resolve_extraction_bucket(
            context,
            default_bucket="local-live",
            s3_bucket_resolver=lambda _: None,
        )
        == "local-live"
    )


def test_cloud_manifest_references_keep_local_paths_for_missing_locations(tmp_path):
    sba_manifest = tmp_path / "sba.json"
    census_manifest = tmp_path / "census.json"
    bls_manifest = tmp_path / "bls.json"
    census_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri="s3://cloud-bucket/manifests/census.json",
        artifact_key="manifests/census.json",
        local_path=None,
        s3_uri="s3://cloud-bucket/manifests/census.json",
    )
    extraction_paths = extraction_paths_from_manifest_maps(
        manifest_paths={
            "sba_7a_fy2020_present": sba_manifest,
            "bds_state_year": census_manifest,
            "laus_state_month": bls_manifest,
        },
        manifest_locations={
            "bds_state_year": census_location,
        },
    )

    assert extraction_paths.manifest_references_for_validation(
        cloud_route=True,
    ) == (
        sba_manifest,
        census_location,
        bls_manifest,
    )


def test_raw_loads_record_cloud_artifact_locations_without_reupload(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "cloud-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-artifact-record",
    )
    manifest_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri="s3://cloud-bucket/manifests/example.json",
        artifact_key="manifests/example.json",
        local_path=None,
        s3_uri="s3://cloud-bucket/manifests/example.json",
    )
    validation_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri="s3://cloud-bucket/validation/results.json",
        artifact_key="validation/results.json",
        local_path=None,
        s3_uri="s3://cloud-bucket/validation/results.json",
    )
    extraction_paths = ExtractionPaths(
        sba_7a_manifest_paths=(),
        sba_504_manifest_paths=(),
        census_bds_manifest_paths=(),
        bls_laus_manifest_paths=(),
        manifest_paths=(),
        manifest_locations=(manifest_location,),
    )
    validation_output = RawValidationOutput(
        local_path=tmp_path / "validation_results.json",
        artifact_location=validation_location,
    )

    summary = raw_loads.record_raw_artifact_locations_for_context(
        context,
        extraction_paths,
        validation_output,
    )

    assert summary.bucket == "cloud-bucket"
    assert summary.uploaded_objects == (
        "s3://cloud-bucket/manifests/example.json",
        "s3://cloud-bucket/validation/results.json",
    )


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
        return SBAExtractionSummary(
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
        return CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
        )

    monkeypatch.setattr(source_extracts, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(source_extracts, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(source_extracts, "extract_bls_laus", fake_bls_extract)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)

    assert [name for name, _ in calls] == ["sba", "census", "bls"]
    assert calls[0][1]["config"] == project_config.sba
    assert calls[0][1]["source_identity"] == project_config.source_identity(
        SBA_FOIA_SOURCE_KEY
    )
    assert calls[1][1]["config"] == project_config.census_bds
    assert calls[1][1]["source_identity"] == project_config.source_identity(
        CENSUS_BDS_SOURCE_KEY
    )
    assert calls[1][1]["start_year"] == 2020
    assert calls[1][1]["end_year"] == 2024
    assert calls[2][1]["config"] == project_config.bls_laus
    assert calls[2][1]["source_identity"] == project_config.source_identity(
        BLS_LAUS_SOURCE_KEY
    )
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
        return ArtifactLocation(
            storage_backend="s3",
            artifact_uri=f"s3://cloud-bucket/manifests/test/{resource_name}.json",
            artifact_key=f"manifests/test/{resource_name}.json",
            local_path=None,
            s3_uri=f"s3://cloud-bucket/manifests/test/{resource_name}.json",
        )

    def fake_sba_extract(**kwargs):
        calls.append(("sba", kwargs))
        return SBAExtractionSummary(
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
        return CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
            manifest_location=fake_manifest_location("bds_state_year"),
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
            manifest_location=fake_manifest_location("laus_state_month"),
        )

    monkeypatch.setattr(source_extracts, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(source_extracts, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(source_extracts, "extract_bls_laus", fake_bls_extract)

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
        return SBAExtractionSummary(
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
        return CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
        )

    monkeypatch.setattr(source_extracts, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(source_extracts, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(source_extracts, "extract_bls_laus", fake_bls_extract)

    local_flow.extract_sources.fn(context, project_config)

    bls_call = [kwargs for name, kwargs in calls if name == "bls"][0]
    assert project_config.bls_laus.start_year == 1990
    assert bls_call["start_year"] == 1989
    assert bls_call["end_year"] == 2024


def test_live_extraction_honors_disabled_sources(tmp_path, monkeypatch):
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        CENSUS_BDS_SOURCE_KEY: replace(
            project_config.sources[CENSUS_BDS_SOURCE_KEY],
            enabled=False,
        ),
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
        return SBAExtractionSummary(
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
        return CensusBDSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
        )

    def fake_bls_extract(**kwargs):
        calls.append(("bls", kwargs))
        return BLSLAUSExtractionSummary(
            result=None,
            manifest_path=_write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
        )

    monkeypatch.setattr(source_extracts, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(source_extracts, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(source_extracts, "extract_bls_laus", fake_bls_extract)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)
    expectations = raw_validation_expectations(
        context.extract_mode,
        project_config,
    )

    assert [name for name, _ in calls] == ["sba", "bls"]
    assert extraction_paths.census_bds_manifest_paths == ()
    assert len(extraction_paths.manifest_paths) == 3
    assert expectations.census_required_variables == ()
    assert expectations.census_expected_state_count == 0


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
