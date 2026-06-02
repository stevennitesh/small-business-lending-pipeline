from __future__ import annotations

from pathlib import Path

import pytest

from pipelines.flows import dbt_bi, run_setup
import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.run_models import LocalRunContext


def test_flow_powerbi_export_dir_can_use_env_override(tmp_path, monkeypatch):
    export_dir = tmp_path / "custom-powerbi"
    monkeypatch.setenv("POWERBI_EXPORT_DIR", str(export_dir))

    context = _flow_context(
        tmp_path,
        pipeline_run_id="local-powerbi-env-override",
    )

    assert context.run_export_dir == export_dir
    assert export_dir.is_dir()


def test_flow_powerbi_export_dir_argument_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("POWERBI_EXPORT_DIR", str(tmp_path / "env-powerbi"))
    export_dir = tmp_path / "arg-powerbi"

    context = _flow_context(
        tmp_path,
        powerbi_export_dir=str(export_dir),
        pipeline_run_id="local-powerbi-arg-override",
    )

    assert context.run_export_dir == export_dir
    assert export_dir.is_dir()


def test_run_setup_initializes_context_directories(tmp_path):
    context = _setup_context(
        tmp_path,
        pipeline_run_id="run-setup",
    )

    assert context.pipeline_run_id == "run-setup"
    assert context.run_mode == "local"
    assert context.data_root.is_dir()
    assert context.run_validation_dir.is_dir()
    assert context.run_export_dir.is_dir()


def test_run_setup_rejects_unknown_run_mode(tmp_path):
    with pytest.raises(ValueError, match="run_mode must be one of: cloud, local"):
        _setup_context(
            tmp_path,
            run_mode="final",
        )


def test_run_setup_resolves_s3_bucket_from_context_before_env(tmp_path, monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "env-bucket")
    context = _setup_context(
        tmp_path,
        run_mode="cloud",
        dbt_target="prod_snowflake",
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

    context = _flow_context(
        tmp_path,
        run_mode="cloud",
        dbt_target="prod_snowflake",
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
    context = _flow_context(
        tmp_path,
        pipeline_run_id="profile-thread-check",
    )

    dbt_bi.ensure_dbt_profile(context)

    profile_text = (tmp_path / "profiles" / "profiles.yml").read_text(encoding="utf-8")
    assert "threads: 1" in profile_text


def _flow_context(
    tmp_path: Path,
    *,
    pipeline_run_id: str,
    run_mode: str = "local",
    dbt_target: str = "dev_duckdb",
    s3_bucket: str | None = None,
    powerbi_export_dir: str | None = None,
) -> LocalRunContext:
    return local_flow.initialize_run.fn(
        run_mode=run_mode,
        extract_mode="fixture",
        dbt_target=dbt_target,
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        powerbi_export_dir=powerbi_export_dir,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
    )


def _setup_context(
    tmp_path: Path,
    *,
    run_mode: str = "local",
    dbt_target: str = "dev_duckdb",
    s3_bucket: str | None = None,
    pipeline_run_id: str | None = None,
) -> LocalRunContext:
    return run_setup.initialize_run_context(
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
