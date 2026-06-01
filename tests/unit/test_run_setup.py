from __future__ import annotations

import pytest

from pipelines.flows import dbt_bi, run_setup
import pipelines.flows.lending_pipeline_flow as local_flow


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


def test_run_setup_initializes_context_directories(tmp_path):
    context = run_setup.initialize_run_context(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        pipeline_run_id="run-setup",
    )

    assert context.pipeline_run_id == "run-setup"
    assert context.run_mode == "local"
    assert context.data_root.is_dir()
    assert context.run_validation_dir.is_dir()
    assert context.run_export_dir.is_dir()


def test_run_setup_resolves_s3_bucket_from_context_before_env(tmp_path, monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "env-bucket")
    context = run_setup.initialize_run_context(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="context-bucket",
        pipeline_run_id="bucket-context",
    )

    assert run_setup.resolve_s3_bucket(context) == "context-bucket"


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
    monkeypatch.setattr(run_setup, "load_dotenv", lambda override=True: None)

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

    with pytest.raises(RuntimeError) as exc_info:
        local_flow.require_cloud_mode_config.fn(context)
    message = str(exc_info.value)
    assert "Missing cloud mode configuration" in message
    assert "S3_BUCKET" in message
    assert "SNOWFLAKE_CONFIG" in message


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

    dbt_bi.ensure_dbt_profile(context)

    profile_text = (tmp_path / "profiles" / "profiles.yml").read_text(
        encoding="utf-8"
    )
    assert "threads: 1" in profile_text
